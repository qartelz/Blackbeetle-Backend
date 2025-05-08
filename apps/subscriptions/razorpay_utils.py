import razorpay
from django.conf import settings
from django.core.exceptions import ValidationError
from decimal import Decimal
import logging
from .models import Order

logger = logging.getLogger(__name__)

# Initialize Razorpay client
client = razorpay.Client(auth=('rzp_test_dyw9PplCmeK8VH', 'settings.RAZORPAY_KEY_SECRET'))

def create_razorpay_order(order: Order) -> dict:
    """
    Create a Razorpay order for the given Order instance.
    
    Args:
        order: Order model instance
        
    Returns:
        dict: Razorpay order details
        
    Raises:
        ValidationError: If order creation fails
    """
    try:
        # Validate order state
        if order.status != 'PENDING':
            raise ValidationError("Can only create Razorpay orders for pending orders")
            
        if order.razorpay_order_id:
            raise ValidationError("Razorpay order already exists for this order")
            
        if order.payment_type != 'RAZORPAY':
            raise ValidationError("Invalid payment type for Razorpay order")

        # Convert amount to paise (Razorpay expects amount in smallest currency unit)
        amount_paise = int(order.amount * 100)
        
        # Create order in Razorpay
        razorpay_order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'payment_capture': '1',  # Auto-capture payment
            'notes': {
                'order_id': str(order.id),
                'user_email': order.user.email,
                'plan_name': order.plan.name
            }
        })
        
        # Update order with Razorpay order ID
        order.razorpay_order_id = razorpay_order['id']
        order.status = 'PROCESSING'
        order.save()
        
        logger.info(f"Created Razorpay order {razorpay_order['id']} for order {order.id}")
        return razorpay_order

    except razorpay.errors.BadRequestError as e:
        logger.error(f"Razorpay BadRequestError for order {order.id}: {str(e)}")
        raise ValidationError(f"Failed to create Razorpay order: {str(e)}")
    except Exception as e:
        logger.error(f"Error creating Razorpay order for order {order.id}: {str(e)}")
        raise ValidationError("Failed to create Razorpay order")

def verify_razorpay_payment_signature(payment_id: str, order_id: str, signature: str) -> bool:
    """
    Verify Razorpay payment signature.
    
    Args:
        payment_id: Razorpay payment ID
        order_id: Razorpay order ID
        signature: Razorpay signature
        
    Returns:
        bool: True if signature is valid
        
    Raises:
        ValidationError: If signature verification fails
    """
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        })
        logger.info(f"Verified signature for payment {payment_id}")
        return True
        
    except razorpay.errors.SignatureVerificationError as e:
        logger.error(f"Signature verification failed for payment {payment_id}: {str(e)}")
        raise ValidationError("Invalid payment signature")
    except Exception as e:
        logger.error(f"Error verifying payment signature for {payment_id}: {str(e)}")
        raise ValidationError("Failed to verify payment signature")

def get_razorpay_order(order_id: str) -> dict:
    """
    Fetch Razorpay order details.
    
    Args:
        order_id: Razorpay order ID
        
    Returns:
        dict: Razorpay order details
        
    Raises:
        ValidationError: If order fetch fails
    """
    try:
        razorpay_order = client.order.fetch(order_id)
        logger.info(f"Fetched Razorpay order {order_id}")
        return razorpay_order
        
    except razorpay.errors.BadRequestError as e:
        logger.error(f"Failed to fetch Razorpay order {order_id}: {str(e)}")
        raise ValidationError(f"Invalid Razorpay order ID: {str(e)}")
    except Exception as e:
        logger.error(f"Error fetching Razorpay order {order_id}: {str(e)}")
        raise ValidationError("Failed to fetch Razorpay order details")

def fetch_payment_details(payment_id: str) -> dict:
    """
    Fetch payment details from Razorpay.
    
    Args:
        payment_id: Razorpay payment ID
        
    Returns:
        dict: Payment details
        
    Raises:
        ValidationError: If payment fetch fails
    """
    try:
        payment = client.payment.fetch(payment_id)
        logger.info(f"Fetched payment details for {payment_id}")
        return payment
        
    except razorpay.errors.BadRequestError as e:
        logger.error(f"Failed to fetch payment {payment_id}: {str(e)}")
        raise ValidationError(f"Invalid payment ID: {str(e)}")
    except Exception as e:
        logger.error(f"Error fetching payment {payment_id}: {str(e)}")
        raise ValidationError("Failed to fetch payment details")

def process_webhook_event(event_data: dict) -> None:
    """
    Process Razorpay webhook events.
    
    Args:
        event_data: Webhook event data from Razorpay
        
    Raises:
        ValidationError: If event processing fails
    """
    try:
        event_type = event_data.get('event')
        if not event_type:
            raise ValidationError("Missing event type in webhook data")

        payment_id = event_data.get('payload', {}).get('payment', {}).get('entity', {}).get('id')
        if not payment_id:
            raise ValidationError("Missing payment ID in webhook data")

        # Find corresponding order
        try:
            order = Order.objects.get(razorpay_payment_id=payment_id)
        except Order.DoesNotExist:
            logger.error(f"Order not found for payment {payment_id}")
            raise ValidationError(f"Order not found for payment {payment_id}")

        if event_type == 'payment.captured':
            if order.status != 'COMPLETED':
                order.status = 'COMPLETED'
                order.save()
                logger.info(f"Payment captured for order {order.id}")
                
        elif event_type == 'payment.failed':
            if order.status != 'FAILED':
                order.status = 'FAILED'
                order.save()
                logger.info(f"Payment failed for order {order.id}")
                
        elif event_type == 'refund.processed':
            if order.status != 'REFUNDED':
                order.status = 'REFUNDED'
                order.save()
                logger.info(f"Refund processed for order {order.id}")

    except Exception as e:
        logger.error(f"Error processing webhook event: {str(e)}")
        raise ValidationError(f"Failed to process webhook event: {str(e)}")