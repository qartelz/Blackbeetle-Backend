from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncWebsocketConsumer
from apps.trades.models import Trade, TradeHistory, Analysis, Insight
from apps.subscriptions.models import Subscription
from .models import Notification, TradeNotification
import logging
import time
import json

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
            
<<<<<<< Updated upstream
            return trade in previous_trades
=======
            # Simply retrieve existing notifications for the user
            notifications_query = Notification.objects.filter(
                recipient=self.user,
                is_read=False
            )
            
            # For premium users, get up to 100 notifications
            if is_premium:
                notifications = notifications_query.order_by('-created_at')[:100]
            else:
                # For regular users, limit to 50
                notifications = notifications_query.order_by('-created_at')[:50]
            
            # Get all trade IDs from the notifications
            trade_ids = [n.trade_id for n in notifications if n.trade_id]
            
            # Fetch all trades and companies in a single query to avoid N+1 problem
            trades_info = {}
            if trade_ids:
                trades = Trade.objects.filter(id__in=trade_ids).select_related('company')
                trades_info = {
                    t.id: {
                        'tradingSymbol': t.company.trading_symbol,
                        'instrumentName': t.company.instrument_type
                    } for t in trades
                }
            
            # Process notifications with trading info
            result = []
            for notif in notifications:
                notif_data = {
                    'id': str(notif.id),
                    'type': notif.notification_type,
                    'message_type': 'trade_completed' if notif.trade_status == 'COMPLETED' else 'trade_update',
                    'short_message': notif.short_message,
                    'detailed_message': notif.detailed_message,
                    'created_at': notif.created_at.isoformat(),
                    'related_url': notif.related_url,
                    'trade_status': notif.trade_status,
                    'trade_id': notif.trade_id,
                    'is_redirectable': notif.is_redirectable,
                    'trade_data': notif.trade_data
                }
                
                # Add trading symbol and instrument name if available
                if notif.trade_id and notif.trade_id in trades_info:
                    trade_info = trades_info[notif.trade_id]
                    notif_data['tradingSymbol'] = trade_info['tradingSymbol']
                    notif_data['instrumentName'] = trade_info['instrumentName']
                
                result.append(notif_data)
            
            return result
        except Exception as e:
            logger.error(f"Error getting unread notifications: {str(e)}")
            return []

    async def new_notification(self, event: Dict) -> None:
        """Handle new notification events"""
        connection_id = self._connection_id
        try:
            if not self.is_connected:
                return
                
            logger.info(f"[{connection_id}] Received notification event for user {self.user.id}")
            
            # Get the message data
            message = event.get('message', {})
            message_type = message.get('message_type', 'trade_update')
            trade_id = message.get('trade_id')
            
            # Log the notification details
            logger.info(f"[{connection_id}] Notification type: {message_type}, trade_id: {trade_id}")
            
            # For trade updates, verify access
            if trade_id and message_type in ['trade_update', 'trade_completed']:
                from apps.trades.models import Trade
                from apps.subscriptions.models import Subscription
                
                # Get user's subscription
                subscription = await sync_to_async(Subscription.objects.filter(
                    user=self.user,
                    is_active=True,
                    end_date__gt=timezone.now()
                ).first)()
                
                if subscription:
                    # Get the trade
                    trade = await sync_to_async(Trade.objects.get)(id=trade_id)
                    
                    # Check if user has access
                    has_access = await sync_to_async(trade.is_trade_accessible)(self.user, subscription)
                    
                    if not has_access:
                        logger.warning(f"[{connection_id}] User {self.user.id} does not have access to trade {trade_id}")
                        return
                    
                    logger.info(f"[{connection_id}] User {self.user.id} has access to trade {trade_id}")
            
            # Send the notification to the client
            await self.send(text_data=json.dumps({
                'type': 'notification',
                'data': message
            }, cls=CustomJSONEncoder))
            
            logger.info(f"[{connection_id}] Successfully sent notification to user {self.user.id}")
            
        except Exception as e:
            logger.error(f"[{connection_id}] Error sending notification: {str(e)}", exc_info=True)

    async def _process_message(self, message_type: str, data: Dict) -> None:
        """Process incoming messages"""
        if message_type == 'mark_read':
            notification_id = data.get('notification_id')
            if notification_id:
                await self._mark_notification_read(notification_id)
>>>>>>> Stashed changes
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


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Handle WebSocket connection"""
        try:
            # Get user from scope
            user = self.scope["user"]
            
            if not user.is_authenticated:
                await self.close()
                return
            
            # Create group name for this user
            self.group_name = f"notification_updates_{user.id}"
            
            # Join the group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            
            await self.accept()
            
            logger.info(f"WebSocket connected for user {user.id}")
        except Exception as e:
            logger.error(f"Error in WebSocket connection: {str(e)}")
            await self.close()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        try:
            # Leave the group
            if hasattr(self, 'group_name'):
                await self.channel_layer.group_discard(
                    self.group_name,
                    self.channel_name
                )
            logger.info(f"WebSocket disconnected with code {close_code}")
        except Exception as e:
            logger.error(f"Error in WebSocket disconnection: {str(e)}")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            # Parse the received JSON
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            if message_type == 'mark_read':
                # Handle marking notifications as read
                notification_ids = text_data_json.get('notification_ids', [])
                if notification_ids:
                    # Update notifications (in a separate thread/async)
                    await self.mark_notifications_read(notification_ids)
            
            logger.info(f"Received WebSocket message: {message_type}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {str(e)}")

    async def notification_message(self, event):
        """Send notification to WebSocket"""
        try:
            # Send message to WebSocket
            await self.send(text_data=json.dumps(event))
            logger.info("Notification sent to WebSocket")
        except Exception as e:
            logger.error(f"Error sending notification to WebSocket: {str(e)}")

    async def mark_notifications_read(self, notification_ids):
        """Mark notifications as read"""
        try:
            user = self.scope["user"]
            # Update notifications in database
            await self.channel_layer.send(
                self.channel_name,
                {
                    "type": "notification_message",
                    "message": {
                        "type": "notifications_marked_read",
                        "notification_ids": notification_ids
                    }
                }
            )
        except Exception as e:
            logger.error(f"Error marking notifications as read: {str(e)}")