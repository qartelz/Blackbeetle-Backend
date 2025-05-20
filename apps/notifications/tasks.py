from celery import shared_task
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
from django.db import DatabaseError
from django.contrib.auth import get_user_model
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from apps.trades.models import Trade
from apps.subscriptions.models import Subscription
from .models import Notification
import logging
import time

logger = logging.getLogger(__name__)

# Constants for batching
BATCH_SIZE = 100  # Process 100 notifications at a time

User = get_user_model()

@shared_task
def process_trade_notifications(trade_id, notification_type, short_message, detailed_message=None):
    """
    Process notifications for a trade in an efficient, batched manner.
    This task handles filtering eligible users, creating notifications, and sending them.
    """
    logger.info(f"Starting notification processing for trade {trade_id}")
    start_time = time.time()
    
    try:
        # Get the trade
        trade = Trade.objects.select_related('company').get(id=trade_id)
        trade_content_type = ContentType.objects.get_for_model(Trade)
        
        # Skip if trade is PENDING
        if trade.status == 'PENDING':
            logger.info(f"Skipping notifications for PENDING trade {trade_id}")
            return
        
        # Get eligible plan levels
        from apps.notifications.signals import NotificationManager
        eligible_plans = NotificationManager.get_plan_levels(trade.plan_type)
        eligible_plans_with_premium = eligible_plans + ['SUPER_PREMIUM', 'FREE_TRIAL']
        
        # Get active subscriptions more efficiently using a single query
        active_subscriptions = Subscription.objects.filter(
            plan__name__in=eligible_plans_with_premium,
            is_active=True,
            start_date__lte=timezone.now(),
            end_date__gt=timezone.now()
        ).select_related('user', 'plan')
        
        # Get existing notifications to avoid duplicates
        existing_notifications = set(Notification.objects.filter(
            trade_id=trade_id,
            notification_type=notification_type
        ).values_list('recipient_id', flat=True))
        
        logger.info(f"Found {active_subscriptions.count()} potentially eligible subscriptions for trade {trade_id}")
        
        # Update redirectable status for completed trades
        if trade.status == 'COMPLETED':
            logger.info(f"Trade {trade_id} is completed, updating old notification status")
            try:
                Notification.objects.filter(
                    trade_id=trade_id,
                    trade_status='ACTIVE'
                ).update(is_redirectable=False)
            except DatabaseError as e:
                logger.error(f"Database error updating redirectable status: {e}")
        
        # Process subscriptions in batches to determine eligible users
        subscription_count = active_subscriptions.count()
        eligible_users = []
        
        for i in range(0, subscription_count, BATCH_SIZE):
            batch = active_subscriptions[i:i+BATCH_SIZE]
            
            # We'll collect user IDs from this batch who are eligible
            batch_eligible_users = []
            
            for subscription in batch:
                # Skip if user already has a notification for this trade/type
                if subscription.user_id in existing_notifications:
                    continue
                
                # Use direct trade accessibility check
                if trade.is_trade_accessible(subscription.user, subscription):
                    batch_eligible_users.append(subscription.user_id)
                    logger.info(f"User {subscription.user_id} with {subscription.plan.name} plan is eligible for notification about trade {trade_id}")
                else:
                    logger.info(f"User {subscription.user_id} with {subscription.plan.name} plan is NOT eligible for notification about trade {trade_id}")
            
            eligible_users.extend(batch_eligible_users)
        
        # Early return if no eligible users
        if not eligible_users:
            logger.info(f"No eligible users found for trade {trade_id} notifications")
            return []
        
        # Create notifications in batches
        logger.info(f"Creating notifications for {len(eligible_users)} eligible users")
        notifications = []
        notification_count = 0
        
        for i in range(0, len(eligible_users), BATCH_SIZE):
            batch_user_ids = eligible_users[i:i+BATCH_SIZE]
            batch_users = User.objects.filter(id__in=batch_user_ids)
            
            batch_notifications = []
            for user in batch_users:
                notification = Notification(
                    recipient=user,
                    notification_type=notification_type,
                    content_type=trade_content_type,
                    object_id=trade.id,
                    short_message=short_message,
                    detailed_message=detailed_message,
                    trade_status=trade.status,
                    is_redirectable=True,
                    trade_id=trade.id,
                    related_url=f"/trades/{trade.id}"
                )
                batch_notifications.append(notification)
            
            # Use bulk_create for efficiency
            created_batch = Notification.objects.bulk_create(batch_notifications)
            notification_count += len(created_batch)
            notifications.extend(created_batch)
            
            logger.info(f"Created batch of {len(created_batch)} notifications for trade {trade_id}")
        
        end_time = time.time()
        logger.info(f"Created {notification_count} notifications for trade {trade_id} in {end_time - start_time:.2f} seconds")
        
        # Send websocket notifications (but don't wait for this to complete)
        if notification_count > 0:
            send_websocket_notifications.delay([n.id for n in notifications])
        
        return notification_count
        
    except Trade.DoesNotExist:
        logger.error(f"Trade {trade_id} not found")
    except Exception as e:
        logger.error(f"Error processing notifications for trade {trade_id}: {str(e)}", exc_info=True)
    
    return 0

@shared_task
def send_websocket_notifications(notification_ids, batch_size=20):
    """Send websocket notifications in batches"""
    logger.info(f"Starting websocket notifications for {len(notification_ids)} notifications")
    start_time = time.time()
    
    channel_layer = get_channel_layer()
    sent_count = 0
    
    # Process in batches to avoid overloading the system
    for i in range(0, len(notification_ids), batch_size):
        batch_ids = notification_ids[i:i+batch_size]
        
        # Get notifications with all related data in one efficient query
        notifications = Notification.objects.filter(
            id__in=batch_ids
        ).select_related('recipient')
        
        for notification in notifications:
            try:
                # Get the trade object with all related data (with optimized queries)
                trade = Trade.objects.select_related(
                    'company', 
                    'analysis'
                ).prefetch_related(
                    'history'
                ).get(id=notification.trade_id)
                
                # Get user's subscription efficiently
                subscription = Subscription.objects.get(
                    user=notification.recipient,
                    is_active=True,
                    start_date__lte=timezone.now(),
                    end_date__gt=timezone.now()
                )
                
                # Get formatted data
                from apps.notifications.signals import NotificationManager
                updated_company = NotificationManager._format_company_with_trade(trade)
                trade_counts = NotificationManager.get_trade_counts(notification.recipient, subscription)
                
                # Get plan limits
                plan_limits = {
                    'BASIC': {'new': 6, 'previous': 6, 'total': 12},
                    'PREMIUM': {'new': 9, 'previous': 6, 'total': 15},
                    'SUPER_PREMIUM': {'new': None, 'previous': 6, 'total': None},
                    'FREE_TRIAL': {'new': None, 'previous': 6, 'total': None}
                }
                
                limits = plan_limits.get(subscription.plan.name, {'new': None, 'previous': 6})
                
                # Calculate remaining slots
                remaining = {
                    'new': None if limits['new'] is None else max(0, limits['new'] - trade_counts['new']),
                    'previous': None if limits['previous'] is None else max(0, limits['previous'] - trade_counts['previous']),
                    'total': None if limits['total'] is None else max(0, limits['total'] - trade_counts['total'])
                }
                
                # Determine message type based on trade status
                message_type = "trade_completed" if notification.trade_status == 'COMPLETED' else "trade_update"
                
                payload = {
                    'type': 'new_notification',
                    'message': {
                        'id': str(notification.id),
                        'type': notification.notification_type,
                        'message_type': message_type,
                        'short_message': notification.short_message,
                        'detailed_message': notification.detailed_message,
                        'created_at': notification.created_at.isoformat(),
                        'related_url': notification.related_url,
                        'trade_status': notification.trade_status,
                        'trade_id': notification.trade_id,
                        'is_redirectable': notification.is_redirectable,
                        'data': {
                            'updated_company': updated_company,
                            'subscription': {
                                'plan': subscription.plan.name,
                                'start_date': subscription.start_date.isoformat(),
                                'end_date': subscription.end_date.isoformat(),
                                'limits': limits,
                                'current': trade_counts,
                                'remaining': remaining
                            }
                        }
                    }
                }
                
                # Send notification via websocket
                async_to_sync(channel_layer.group_send)(
                    f"notification_updates_{notification.recipient.id}",
                    payload
                )
                
                sent_count += 1
                
            except Exception as e:
                logger.error(f"Error sending websocket notification {notification.id}: {str(e)}")
        
        # Small sleep between batches to avoid overwhelming the websocket server
        if i + batch_size < len(notification_ids):
            time.sleep(0.1)
    
    end_time = time.time()
    logger.info(f"Sent {sent_count} websocket notifications in {end_time - start_time:.2f} seconds")
    return sent_count 