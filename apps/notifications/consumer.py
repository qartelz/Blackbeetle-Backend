from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from apps.trades.models import Trade, TradeHistory, Analysis, Insight
from apps.subscriptions.models import Subscription
from .models import Notification, TradeNotification
import logging
import time

logger = logging.getLogger(__name__)

# Flag to control which notification system to use
USE_LEGACY_NOTIFICATION = False  # Set to False to use the new system


class UnifiedTradeNotificationManager:
    """Unified manager to handle trade notifications consistently"""
    
    @staticmethod
    def is_trade_accessible(user, trade, subscription):
        """Consistent method to check if a trade is accessible to a user"""
        # Always use trade model's method if available
        if hasattr(trade, 'is_trade_accessible'):
            return trade.is_trade_accessible(user, subscription)
            
        # Fallback to manual logic if method doesn't exist
        subscription_start = subscription.start_date
        plan_name = subscription.plan.name
        
        # Process SUPER_PREMIUM and FREE_TRIAL users
        if plan_name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
            return True
            
        # Get plan hierarchy
        plan_hierarchy = {
            'BASIC': ['BASIC'],
            'PREMIUM': ['BASIC', 'PREMIUM'],
            'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM'],
            'FREE_TRIAL': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
        }
        
        # Check if trade's plan is in user's plan hierarchy
        if trade.plan_type not in plan_hierarchy.get(plan_name, []):
            return False
            
        # Get trade limits
        trade_limits = {
            'BASIC': 6,
            'PREMIUM': 9,
            'SUPER_PREMIUM': float('inf'),
            'FREE_TRIAL': float('inf')
        }
        
        # If trade was created before subscription, it's a "previous trade"
        if trade.created_at < subscription_start:
            # All plans can access up to 6 previous trades
            previous_trades = Trade.objects.filter(
                created_at__lt=subscription_start,
                plan_type__in=plan_hierarchy.get(plan_name, []),
                status__in=['ACTIVE', 'COMPLETED']
            ).order_by('-created_at')[:6]
            
            return trade in previous_trades
        else:
            # For new trades, respect the plan limits
            new_trades = Trade.objects.filter(
                created_at__gte=subscription_start,
                plan_type__in=plan_hierarchy.get(plan_name, []),
                status__in=['ACTIVE', 'COMPLETED']
            ).order_by('created_at')[:trade_limits.get(plan_name, 0)]
            
            return trade in new_trades
    
    @staticmethod
    def get_eligible_subscribers(trade, batch_size=100):
        """Get users who should receive notifications for this trade"""
        # Get active subscriptions
        active_subscriptions = Subscription.objects.filter(
            is_active=True,
            start_date__lte=timezone.now(),
            end_date__gt=timezone.now()
        ).select_related('user', 'plan')
        
        # Get existing notifications to avoid duplicates
        existing_notifications = set(
            list(Notification.objects.filter(trade_id=trade.id).values_list('recipient_id', flat=True)) + 
            list(TradeNotification.objects.filter(trade_id=trade.id).values_list('user_id', flat=True))
        )
        
        subscription_count = active_subscriptions.count()
        eligible_users = []
        
        logger.info(f"Processing {subscription_count} subscriptions for eligibility")
        
        # Process in batches for performance
        for i in range(0, subscription_count, batch_size):
            batch = active_subscriptions[i:i+batch_size]
            batch_eligible = []
            
            for subscription in batch:
                # Skip if user already has a notification
                if subscription.user_id in existing_notifications:
                    continue
                    
                # Check if user should receive this notification
                if UnifiedTradeNotificationManager.is_trade_accessible(
                    subscription.user, trade, subscription
                ):
                    batch_eligible.append(subscription.user_id)
            
            eligible_users.extend(batch_eligible)
            
        logger.info(f"Total eligible users for trade {trade.id}: {len(eligible_users)}")
        return eligible_users
    
    @staticmethod
    def process_trade_notification(trade_id, notification_type, short_message, detailed_message=None):
        """Process trade notification - used by Celery task"""
        try:
            # Get the trade
            trade = Trade.objects.get(id=trade_id)
            
            # Skip for PENDING trades
            if trade.status == 'PENDING':
                return
                
            # Create notifications based on which system to use
            if USE_LEGACY_NOTIFICATION:
                # Use the original NotificationManager system
                from .notifications import NotificationManager
                notifications = NotificationManager.create_notification(
                    trade, notification_type, short_message, detailed_message
                )
                NotificationManager.send_websocket_notifications(notifications)
            else:
                # Use the TradeSignalHandler system
                # This is a simplified version that creates TradeNotifications
                eligible_users = UnifiedTradeNotificationManager.get_eligible_subscribers(trade)
                
                # Get active subscriptions for eligible users
                subscriptions = Subscription.objects.filter(
                    user_id__in=eligible_users,
                    is_active=True
                ).select_related('user', 'plan')
                
                # Prepare trade data
                from .trade_signal_handler import TradeUpdateManager
                trade_data = TradeUpdateManager.prepare_trade_data(
                    trade, "updated" if trade.status == "ACTIVE" else "completed"
                )
                
                # Get channel layer
                channel_layer = get_channel_layer()
                
                for subscription in subscriptions:
                    user = subscription.user
                    
                    # Check if we should send notification
                    if UnifiedTradeNotificationManager.is_trade_accessible(user, trade, subscription):
                        # Create notification
                        trade_notification_type = (
                            TradeNotification.NotificationType.TRADE_COMPLETED 
                            if trade.status == 'COMPLETED' 
                            else TradeNotification.NotificationType.TRADE_UPDATE
                        )
                        
                        TradeNotification.create_trade_notification(
                            user=user,
                            trade=trade,
                            notification_type=trade_notification_type,
                            message=short_message
                        )
                        
                        # Send WebSocket update
                        group_name = f"trade_updates_{user.id}"
                        
                        # Customize message for this user
                        user_trade_data = trade_data.copy()
                        
                        async_to_sync(channel_layer.group_send)(
                            group_name,
                            {
                                "type": "trade_update",
                                "data": user_trade_data
                            }
                        )
                        
                        # Also send to notification channel
                        notification_group = f"notification_updates_{user.id}"
                        
                        # Format notification payload
                        notification_payload = {
                            'type': 'new_notification',
                            'message': {
                                'type': notification_type,
                                'message_type': "trade_completed" if trade.status == 'COMPLETED' else "trade_update",
                                'short_message': short_message,
                                'detailed_message': detailed_message,
                                'created_at': timezone.now().isoformat(),
                                'trade_status': trade.status,
                                'trade_id': trade.id,
                                'is_redirectable': True,
                                'data': {
                                    'updated_company': {
                                        'id': trade.company.id,
                                        'tradingSymbol': trade.company.trading_symbol,
                                        'exchange': trade.company.exchange
                                    }
                                }
                            }
                        }
                        
                        async_to_sync(channel_layer.group_send)(
                            notification_group,
                            notification_payload
                        )
                    
        except Exception as e:
            logger.error(f"Error processing trade notification: {str(e)}", exc_info=True)


@receiver(post_save, sender=Trade)
def unified_trade_signal_handler(sender, instance, created, **kwargs):
    """Unified signal handler for Trade model"""
    logger.info(f"Trade signal received - ID: {instance.id}, Status: {instance.status}, Created: {created}")
    
    try:
        # Skip notifications for PENDING trades
        if instance.status == 'PENDING':
            logger.info(f"Skipping notification for PENDING trade {instance.id}")
            return
            
        # Import the Celery task
        from .tasks import process_trade_notifications
        
        if created:
            # New trade notification
            logger.info(f"Queueing notification task for new trade {instance.id}")
            short_message = f"New trade alert: {instance.company.trading_symbol}"
            detailed_message = f"A new trade has been created for {instance.company.trading_symbol}"
        else:
            # Trade status update notification
            if instance.status == 'COMPLETED':
                logger.info(f"Queueing notification task for completed trade {instance.id}")
                short_message = f"Trade completed: {instance.company.trading_symbol}"
                detailed_message = f"The trade for {instance.company.trading_symbol} has been completed"
            else:
                logger.info(f"Queueing notification task for updated trade {instance.id}")
                short_message = f"Trade updated: {instance.company.trading_symbol}"
                detailed_message = f"The trade for {instance.company.trading_symbol} has been updated"
        
        # Queue the task to execute asynchronously
        transaction.on_commit(
            lambda: process_trade_notifications.delay(
                instance.id, 'TRADE', short_message, detailed_message
            )
        )
    except Exception as e:
        logger.error(f"Error queueing notification task for trade {instance.id}: {str(e)}", exc_info=True)


# Keep the other signal handlers as they are
@receiver(post_save, sender=TradeHistory)
def handle_trade_history_updates(sender, instance, created, **kwargs):
    """Handle notifications for price target updates"""
    if created and instance.trade.status == 'ACTIVE':
        try:
            # Import the Celery task
            from .tasks import process_trade_notifications
            
            short_message = f"Price targets updated: {instance.trade.company.trading_symbol}"
            detailed_message = f"New price targets set - Buy: {instance.buy}, Target: {instance.target}, SL: {instance.sl}"
            
            # Queue the task to execute asynchronously
            transaction.on_commit(
                lambda: process_trade_notifications.delay(
                    instance.trade.id, 'PRICE', short_message, detailed_message
                )
            )
        except Exception as e:
            logger.error(f"Error queueing notification task for trade history {instance.id}: {str(e)}", exc_info=True)


@receiver(post_save, sender=Analysis)
def handle_analysis_updates(sender, instance, created, **kwargs):
    """Handle notifications for analysis updates"""
    if instance.trade.status == 'ACTIVE':
        try:
            # Import the Celery task
            from .tasks import process_trade_notifications
            
            action = "created" if created else "updated"
            short_message = f"Analysis {action}: {instance.trade.company.trading_symbol}"
            detailed_message = f"Trade analysis has been {action}"
            
            # Queue the task to execute asynchronously
            transaction.on_commit(
                lambda: process_trade_notifications.delay(
                    instance.trade.id, 'ANALYSIS', short_message, detailed_message
                )
            )
        except Exception as e:
            logger.error(f"Error queueing notification task for analysis {instance.id}: {str(e)}", exc_info=True)


@receiver(post_save, sender=Insight)
def handle_insight_updates(sender, instance, created, **kwargs):
    """Handle notifications for insight updates"""
    if instance.trade.status == 'COMPLETED':
        try:
            # Check which fields were updated
            if not created:
                updated_fields = []
                if instance.tracker.has_changed('prediction_description'):
                    updated_fields.append('prediction')
                if instance.tracker.has_changed('actual_description'):
                    updated_fields.append('actual outcome')
                if instance.tracker.has_changed('accuracy_score'):
                    updated_fields.append('accuracy score')
                
                if not updated_fields:
                    return
                    
                field_text = ", ".join(updated_fields)
            else:
                field_text = "all details"
            
            # Import the Celery task
            from .tasks import process_trade_notifications
            
            action = "created" if created else "updated"
            short_message = f"Trade insight {action}: {instance.trade.company.trading_symbol}"
            detailed_message = f"Trade insight {action} with updates to {field_text}"
            
            # Queue the task to execute asynchronously
            transaction.on_commit(
                lambda: process_trade_notifications.delay(
                    instance.trade.id, 'INSIGHT', short_message, detailed_message
                )
            )
        except Exception as e:
            logger.error(f"Error queueing notification task for insight {instance.id}: {str(e)}", exc_info=True)

# from channels.generic.websocket import AsyncWebsocketConsumer
# from asgiref.sync import sync_to_async
# from typing import Dict, List, Optional, Any
# import json
# from decimal import Decimal
# from django.utils import timezone
# from urllib.parse import parse_qs
# from rest_framework_simplejwt.authentication import JWTAuthentication
# from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
# import logging
# import asyncio
# from dataclasses import dataclass
# from enum import Enum
# import uuid
# from django.db import transaction
# from django.core.cache import cache
# from django.contrib.contenttypes.models import ContentType

# logger = logging.getLogger(__name__)

# # Database-specific sync_to_async decorator
# db_sync_to_async = sync_to_async(thread_sensitive=True)

# class WebSocketCloseCode(Enum):
#     """Enumeration of WebSocket close codes for better error handling"""
#     NO_TOKEN = 4001
#     INVALID_TOKEN = 4002
#     AUTH_FAILED = 4003
#     UNEXPECTED_AUTH_ERROR = 4004
#     NO_SUBSCRIPTION = 4005
#     GENERAL_ERROR = 4006
#     MAX_RETRIES_EXCEEDED = 4007

# @dataclass
# class ConnectionConfig:
#     """Configuration settings for WebSocket connection"""
#     RECONNECT_DELAY: int = 2  # seconds
#     MAX_RETRIES: int = 3
#     HEARTBEAT_INTERVAL: int = 30  # seconds
#     CONNECTION_TIMEOUT: int = 5  # seconds
#     CACHE_TIMEOUT: int = 3600  # seconds (1 hour)

# class CustomJSONEncoder(json.JSONEncoder):
#     """Custom JSON encoder to handle Decimal, UUID, and datetime types"""
#     def default(self, obj: Any) -> Any:
#         if isinstance(obj, Decimal):
#             return str(obj)
#         if isinstance(obj, uuid.UUID):
#             return str(obj)
#         # Add datetime handling if needed
#         return super().default(obj)

# class BaseConsumer(AsyncWebsocketConsumer):
#     """
#     Base WebSocket consumer with improved connection handling, authentication, 
#     and error management.
#     """
    
#     SUCCESS_MESSAGES = {
#         "connected": "Successfully connected.",
#         "initial_data": "Initial data loaded successfully.",
#         "update": "Update received successfully."
#     }
    
#     def __init__(self, *args: Any, **kwargs: Any) -> None:
#         super().__init__(*args, **kwargs)
#         self.user = None
#         self.is_connected = False
#         self.connection_retries = 0
#         self.config = ConnectionConfig()
#         self.heartbeat_task = None
#         self.user_group = None
#         self._connection_id = str(uuid.uuid4())[:8]  # For tracking connections
        
#     async def connect(self) -> None:
#         """Handle WebSocket connection with improved reliability"""
#         connection_id = self._connection_id
#         logger.info(f"[{connection_id}] Connection attempt ({self.connection_retries+1}/{self.config.MAX_RETRIES+1})")
        
#         if self.connection_retries >= self.config.MAX_RETRIES:
#             logger.warning(f"[{connection_id}] Max retries exceeded")
#             await self.close(code=WebSocketCloseCode.MAX_RETRIES_EXCEEDED.value)
#             return

#         try:
#             # First authenticate before accepting the connection
#             if not await self._authenticate():
#                 return  # Auth method handles closing

#             # Then accept the connection
#             await self.accept()
#             logger.info(f"[{connection_id}] Connection accepted for user {self.user.id}")
            
#             # Set up user group and start heartbeat
#             if await self._setup_user_group():
#                 self.is_connected = True
                
#                 # Start heartbeat monitor
#                 self.heartbeat_task = asyncio.create_task(
#                     self._heartbeat_monitor(), 
#                     name=f"heartbeat_{self._connection_id}"
#                 )
                
#                 # Send success confirmation
#                 await self.send_success("connected")
                
#                 # Send initial data
#                 await self.send_initial_data()
#             else:
#                 await self.close(code=WebSocketCloseCode.GENERAL_ERROR.value)

#         except asyncio.TimeoutError:
#             logger.error(f"[{connection_id}] Connection timeout")
#             await self.close(code=1001)  # Going away
#         except Exception as e:
#             logger.error(f"[{connection_id}] Connection error: {str(e)}", exc_info=True)
#             await self.close(code=WebSocketCloseCode.GENERAL_ERROR.value)
            
#             # Implement retry with exponential backoff
#             self.connection_retries += 1
#             backoff_time = self.config.RECONNECT_DELAY * (2 ** (self.connection_retries - 1))
#             await asyncio.sleep(backoff_time)
#             await self.connect()

#     async def _authenticate(self) -> bool:
#         """Authenticate user from JWT token"""
#         connection_id = self._connection_id
#         try:
#             query_string = self.scope.get('query_string', b'').decode('utf-8')
#             token = parse_qs(query_string).get('token', [None])[0]
            
#             if not token:
#                 logger.warning(f"[{connection_id}] No token provided")
#                 await self.close(code=WebSocketCloseCode.NO_TOKEN.value)
#                 return False

#             async with asyncio.timeout(self.config.CONNECTION_TIMEOUT):
#                 jwt_auth = JWTAuthentication()
#                 validated_token = await sync_to_async(jwt_auth.get_validated_token)(token)
#                 self.user = await sync_to_async(jwt_auth.get_user)(validated_token)
            
#             if not self.user or not self.user.is_authenticated:
#                 logger.warning(f"[{connection_id}] Authentication failed")
#                 await self.close(code=WebSocketCloseCode.AUTH_FAILED.value)
#                 return False
                
#             logger.info(f"[{connection_id}] Authentication successful for user {self.user.id}")
#             return True

#         except (InvalidToken, TokenError) as e:
#             logger.error(f"[{connection_id}] Token validation error: {str(e)}")
#             await self.close(code=WebSocketCloseCode.INVALID_TOKEN.value)
#             return False
#         except Exception as e:
#             logger.error(f"[{connection_id}] Unexpected authentication error: {str(e)}", exc_info=True)
#             await self.close(code=WebSocketCloseCode.UNEXPECTED_AUTH_ERROR.value)
#             return False

#     async def _setup_user_group(self) -> bool:
#         """Set up user's channel group - override in subclasses"""
#         # This should be implemented by subclasses
#         raise NotImplementedError("Subclasses must implement _setup_user_group")

#     async def send_initial_data(self) -> None:
#         """Send initial data - override in subclasses"""
#         # This should be implemented by subclasses
#         raise NotImplementedError("Subclasses must implement send_initial_data")

#     async def _heartbeat_monitor(self) -> None:
#         """Send periodic heartbeats to keep connection alive"""
#         connection_id = self._connection_id
#         logger.info(f"[{connection_id}] Starting heartbeat monitor")
        
#         while self.is_connected:
#             try:
#                 await self.send(text_data=json.dumps({
#                     'type': 'heartbeat',
#                     'timestamp': timezone.now().isoformat()
#                 }, cls=CustomJSONEncoder))
                
#                 await asyncio.sleep(self.config.HEARTBEAT_INTERVAL)
#             except asyncio.CancelledError:
#                 logger.info(f"[{connection_id}] Heartbeat monitor cancelled")
#                 break
#             except Exception as e:
#                 logger.error(f"[{connection_id}] Heartbeat error: {str(e)}")
#                 break
                
#         logger.info(f"[{connection_id}] Heartbeat monitor stopped")

#     async def disconnect(self, close_code: int) -> None:
#         """Handle clean disconnection and resource cleanup"""
#         connection_id = self._connection_id
#         logger.info(f"[{connection_id}] Disconnecting with code {close_code}")
        
#         try:
#             # Clean up user group
#             if self.user_group and self.channel_name:
#                 await self.channel_layer.group_discard(
#                     self.user_group, 
#                     self.channel_name
#                 )
#                 logger.info(f"[{connection_id}] Removed from group {self.user_group}")
            
#             # Clean up state
#             self.is_connected = False
            
#             # Cancel heartbeat task
#             if self.heartbeat_task and not self.heartbeat_task.done():
#                 self.heartbeat_task.cancel()
#                 try:
#                     await self.heartbeat_task
#                 except asyncio.CancelledError:
#                     pass
#                 logger.info(f"[{connection_id}] Heartbeat task cancelled")
            
#             # Cancel any consumer-specific tasks
#             await self._cancel_tasks()
                
#         except Exception as e:
#             logger.error(f"[{connection_id}] Error during disconnect: {str(e)}", exc_info=True)

#     async def _cancel_tasks(self) -> None:
#         """Cancel consumer-specific tasks - override in subclasses if needed"""
#         pass

#     async def receive(self, text_data: str) -> None:
#         """Handle incoming messages with validation"""
#         connection_id = self._connection_id
        
#         try:
#             data = json.loads(text_data)
#             message_type = data.get('type')
            
#             if message_type == 'heartbeat_response':
#                 logger.debug(f"[{connection_id}] Received heartbeat response")
#                 return
            
#             logger.info(f"[{connection_id}] Received message type: {message_type}")
            
#             # Process message based on type
#             await self._process_message(message_type, data)
            
#         except json.JSONDecodeError:
#             logger.error(f"[{connection_id}] Invalid JSON received")
#             await self.send(text_data=json.dumps({
#                 'type': 'error',
#                 'message': 'Invalid message format'
#             }, cls=CustomJSONEncoder))
#         except Exception as e:
#             logger.error(f"[{connection_id}] Error processing message: {str(e)}", exc_info=True)

#     async def _process_message(self, message_type: str, data: Dict) -> None:
#         """Process message based on type - override in subclasses"""
#         # Default acknowledgment
#         await self.send(text_data=json.dumps({
#             'type': 'acknowledgment',
#             'message': f'Received message of type: {message_type}'
#         }, cls=CustomJSONEncoder))

#     async def send_success(self, event: str, extra_info: str = None) -> None:
#         """Send a success message to the client"""
#         message = self.SUCCESS_MESSAGES.get(event, "Operation completed successfully.")
#         if extra_info:
#             message += f" {extra_info}"
            
#         await self.send(text_data=json.dumps({
#             "type": "success",
#             "event": event,
#             "message": message,
#             "timestamp": timezone.now().isoformat()
#         }, cls=CustomJSONEncoder))

#     async def send_error(self, code: int, extra_info: str = None) -> None:
#         """Send an error message to the client"""
#         try:
#             error_code = WebSocketCloseCode(code)
#             message = f"Error {code}: {error_code.name}"
#         except ValueError:
#             message = f"Error {code}"
            
#         if extra_info:
#             message += f". Details: {extra_info}"
            
#         await self.send(text_data=json.dumps({
#             "type": "error",
#             "code": code,
#             "message": message,
#             "timestamp": timezone.now().isoformat()
#         }, cls=CustomJSONEncoder))

# class NotificationConsumer(BaseConsumer):
#     """
#     WebSocket consumer for handling real-time notifications.
#     """
#     async def _setup_user_group(self) -> bool:
#         """Set up user's notification group"""
#         try:
#             if self.user:
#                 # Use a distinct prefix for notification groups
#                 self.user_group = f"notification_updates_{self.user.id}"
#                 await self.channel_layer.group_add(
#                     self.user_group,
#                     self.channel_name
#                 )
#                 return True
#             return False
#         except Exception as e:
#             logger.error(f"Error setting up user group: {str(e)}")
#             return False

#     async def send_initial_data(self) -> None:
#         """Send initial notification data"""
#         connection_id = self._connection_id
#         try:
#             if not self.is_connected:
#                 return
                
#             # Get user's unread notifications
#             notifications = await self._get_unread_notifications()
            
#             data = {
#                 'notifications': notifications,
#                 'user_group': self.user_group,
#                 'connected_at': timezone.now().isoformat(),
#                 'user_id': self.user.id,
#                 'connection_id': connection_id
#             }
            
#             await self.send(text_data=json.dumps({
#                 'type': 'initial_data',
#                 'data': data
#             }, cls=CustomJSONEncoder))
            
#             await self.send_success("initial_data")
            
#         except Exception as e:
#             logger.error(f"[{connection_id}] Error sending initial data: {str(e)}", exc_info=True)
#             if self.is_connected:
#                 await self.send(text_data=json.dumps({
#                     'type': 'error',
#                     'message': "Failed to load initial data"
#                 }, cls=CustomJSONEncoder))

#     @db_sync_to_async
#     def _get_unread_notifications(self):
#         """Get user's unread notifications"""
#         from .models import Notification
#         from apps.subscriptions.models import Subscription
#         from apps.trades.models import Trade, Company
        
#         try:
#             # Check if user has a premium subscription
#             is_premium = False
#             try:
#                 subscription = Subscription.objects.get(
#                     user=self.user,
#                     is_active=True,
#                     end_date__gt=timezone.now()
#                 )
#                 is_premium = subscription.plan.name in ['SUPER_PREMIUM', 'FREE_TRIAL']
#             except Subscription.DoesNotExist:
#                 pass
            
#             # Simply retrieve existing notifications for the user
#             notifications_query = Notification.objects.filter(
#                 recipient=self.user,
#                 is_read=False
#             )
            
#             # For premium users, get up to 100 notifications
#             if is_premium:
#                 notifications = notifications_query.order_by('-created_at')[:100]
#             else:
#                 # For regular users, limit to 50
#                 notifications = notifications_query.order_by('-created_at')[:50]
            
#             # Get all trade IDs from the notifications
#             trade_ids = [n.trade_id for n in notifications if n.trade_id]
            
#             # Fetch all trades and companies in a single query to avoid N+1 problem
#             trades_info = {}
#             if trade_ids:
#                 trades = Trade.objects.filter(id__in=trade_ids).select_related('company')
#                 trades_info = {
#                     t.id: {
#                         'tradingSymbol': t.company.trading_symbol,
#                         'instrumentName': t.company.instrument_type
#                     } for t in trades
#                 }
            
#             # Process notifications with trading info
#             result = []
#             for notif in notifications:
#                 notif_data = {
#                     'id': str(notif.id),
#                     'type': notif.notification_type,
#                     'message_type': 'trade_completed' if notif.trade_status == 'COMPLETED' else 'trade_update',
#                     'short_message': notif.short_message,
#                     'detailed_message': notif.detailed_message,
#                     'created_at': notif.created_at.isoformat(),
#                     'related_url': notif.related_url,
#                     'trade_status': notif.trade_status,
#                     'trade_id': notif.trade_id,
#                     'is_redirectable': notif.is_redirectable,
#                     'trade_data': notif.trade_data
#                 }
                
#                 # Add trading symbol and instrument name if available
#                 if notif.trade_id and notif.trade_id in trades_info:
#                     trade_info = trades_info[notif.trade_id]
#                     notif_data['tradingSymbol'] = trade_info['tradingSymbol']
#                     notif_data['instrumentName'] = trade_info['instrumentName']
                
#                 result.append(notif_data)
            
#             return result
#         except Exception as e:
#             logger.error(f"Error getting unread notifications: {str(e)}")
#             return []

#     async def new_notification(self, event: Dict) -> None:
#         """Handle new notification events"""
#         connection_id = self._connection_id
#         try:
#             if not self.is_connected:
#                 return
                
#             logger.info(f"[{connection_id}] Received notification event for user {self.user.id}")
            
#             # Get the message data
#             message = event.get('message', {})
#             message_type = message.get('message_type', 'trade_update')
            
#             # Log the notification details
#             logger.info(f"[{connection_id}] Notification type: {message_type}, trade_id: {message.get('trade_id')}")
            
#             # Send the notification to the client
#             await self.send(text_data=json.dumps({
#                 'type': 'notification',
#                 'data': message
#             }, cls=CustomJSONEncoder))
            
#             logger.info(f"[{connection_id}] Successfully sent notification to user {self.user.id}")
            
#         except Exception as e:
#             logger.error(f"[{connection_id}] Error sending notification: {str(e)}", exc_info=True)

#     async def _process_message(self, message_type: str, data: Dict) -> None:
#         """Process incoming messages"""
#         if message_type == 'mark_read':
#             notification_id = data.get('notification_id')
#             if notification_id:
#                 await self._mark_notification_read(notification_id)
#         else:
#             await super()._process_message(message_type, data)

#     @db_sync_to_async
#     def _mark_notification_read(self, notification_id):
#         """Mark a notification as read"""
#         from .models import Notification
#         try:
#             notification = Notification.objects.get(
#                 id=notification_id,
#                 recipient=self.user
#             )
#             notification.is_read = True
#             notification.save()
            
#             return {
#                 'id': str(notification.id),
#                 'is_read': True
#             }
#         except Notification.DoesNotExist:
#             logger.warning(f"Notification {notification_id} not found for user {self.user.id}")
#             return None