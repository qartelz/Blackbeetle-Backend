from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from decimal import Decimal
from apps.trades.models import Trade, TradeHistory, Analysis, Insight
from apps.subscriptions.models import Subscription
from .models import Notification
from django.db import DatabaseError
import logging
import time
logger = logging.getLogger(__name__)

class NotificationManager:
    @staticmethod
    def _format_trade(trade):
        """Format trade data for notification response."""
        if not trade:
            return None
            
        try:
            formatted_trade = {
                'id': trade.id,
                'trade_type': trade.trade_type,
                'status': trade.status,
                'plan_type': trade.plan_type,
                'warzone': str(trade.warzone),
                'image': trade.image.url if trade.image else None,
                'warzone_history': trade.warzone_history or [],
                'analysis': None,
                'trade_history': []
            }

            # Add analysis data if available
            if hasattr(trade, 'analysis') and trade.analysis:
                formatted_trade['analysis'] = {
                    'bull_scenario': trade.analysis.bull_scenario,
                    'bear_scenario': trade.analysis.bear_scenario,
                    'status': trade.analysis.status,
                    'completed_at': trade.analysis.completed_at.isoformat() if trade.analysis.completed_at else None,
                    'created_at': trade.analysis.created_at.isoformat(),
                    'updated_at': trade.analysis.updated_at.isoformat()
                }

            # Add trade history if available
            if hasattr(trade, 'history'):
                history_items = list(trade.history.all())
                formatted_trade['trade_history'] = []
                
                for history in history_items:
                    history_item = {
                        'buy': str(history.buy),
                        'target': str(history.target),
                        'sl': str(history.sl),
                        'timestamp': history.timestamp.isoformat(),
                    }
                    
                    # Add risk/reward metrics if they exist
                    if hasattr(history, 'risk_reward_ratio'):
                        history_item['risk_reward_ratio'] = str(history.risk_reward_ratio)
                    
                    if hasattr(history, 'potential_profit_percentage'):
                        history_item['potential_profit_percentage'] = str(history.potential_profit_percentage)
                    
                    if hasattr(history, 'stop_loss_percentage'):
                        history_item['stop_loss_percentage'] = str(history.stop_loss_percentage)
                    
                    formatted_trade['trade_history'].append(history_item)

            return formatted_trade

        except Exception as e:
            logger.error(f"Error formatting trade {trade.id}: {str(e)}")
            return None

    @staticmethod
    def _format_company_with_trade(trade):
        """Format company data with trade information."""
        try:
            company = trade.company
            
            # Format the trade
            formatted_trade = NotificationManager._format_trade(trade)
            
            # Create company data structure
            company_data = {
                'id': company.id,
                'tradingSymbol': company.trading_symbol,
                'exchange': company.exchange,
                'instrumentName': company.instrument_type,  # You might want to map this like in trade consumer
                'intraday_trade': formatted_trade if trade.trade_type == 'INTRADAY' else None,
                'positional_trade': formatted_trade if trade.trade_type == 'POSITIONAL' else None,
                'created_at': trade.created_at.isoformat()
            }
            
            return company_data
            
        except Exception as e:
            logger.error(f"Error formatting company data for trade {trade.id}: {str(e)}")
            return None

    @staticmethod
    def get_plan_levels(plan_type):
        """Returns list of plan levels that can access trades of given plan type"""
        plan_hierarchy = {
            'BASIC': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM'],
            'PREMIUM': ['PREMIUM', 'SUPER_PREMIUM'],
            'SUPER_PREMIUM': ['SUPER_PREMIUM']
        }
        return plan_hierarchy.get(plan_type, [])

    @staticmethod
    def get_accessible_trades(user, subscription):
        """Get list of trade IDs accessible to the user based on their subscription."""
        subscription_start = subscription.start_date
        plan_name = subscription.plan.name
        plan_levels = NotificationManager.get_plan_levels(plan_name)
        
        # Special handling for SUPER_PREMIUM and FREE_TRIAL users
        if plan_name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
            # Only get trades that are truly accessible based on subscription timeframe
            # instead of returning ALL trades unconditionally
            all_trades = Trade.objects.filter(
                status__in=['ACTIVE', 'COMPLETED']
            )
            
            # Filter trades to only include those that are accessible according to model logic
            accessible_trades = [t.id for t in all_trades if t.is_trade_accessible(user, subscription)]
            
            return {
                'previous_trades': accessible_trades,
                'new_trades': accessible_trades
            }
        
        # Normal handling for other subscription types - keep the existing logic
        
        # Get previous trades (fixed set of 6)
        previous_trades = Trade.objects.filter(
            created_at__lt=subscription_start,
            plan_type__in=plan_levels,
            status__in=['ACTIVE', 'COMPLETED']
        ).order_by('-created_at')[:6].values_list('id', flat=True)
        
        # Get new trades based on plan limits
        new_trades_query = Trade.objects.filter(
            created_at__gte=subscription_start,
            plan_type__in=plan_levels,
            status__in=['ACTIVE', 'COMPLETED']
        ).order_by('created_at')
        
        # Apply plan-specific limits
        if plan_name == 'BASIC':
            new_trades = new_trades_query[:6]
        elif plan_name == 'PREMIUM':
            new_trades = new_trades_query[:9]
        else:
            # Default behavior for other plans
            new_trades = new_trades_query.all()
        
        new_trade_ids = list(new_trades.values_list('id', flat=True))
        
        return {
            'previous_trades': list(previous_trades),
            'new_trades': new_trade_ids
        }

    @staticmethod
    def get_eligible_subscribers(trade, batch_size=100):
        """Get list of user IDs eligible to receive notifications for this trade"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Get active subscriptions with plans that can access this trade
        eligible_plans = NotificationManager.get_plan_levels(trade.plan_type)
        eligible_plans_with_premium = eligible_plans + ['SUPER_PREMIUM', 'FREE_TRIAL']
        
        # Get active subscriptions for eligible plans more efficiently
        active_subscriptions = Subscription.objects.filter(
            plan__name__in=eligible_plans_with_premium,
            is_active=True,
            start_date__lte=timezone.now(),
            end_date__gt=timezone.now()
        ).select_related('user', 'plan')
        
        # Get existing notifications to avoid duplicates
        existing_notifications = set(Notification.objects.filter(
            trade_id=trade.id
        ).values_list('recipient_id', flat=True))
        
        # Process subscriptions in batches
        subscription_count = active_subscriptions.count()
        eligible_users = []
        
        logger.info(f"Processing {subscription_count} subscriptions for eligibility in batches of {batch_size}")
        
        for i in range(0, subscription_count, batch_size):
            start_time = time.time()
            batch = active_subscriptions[i:i+batch_size]
            batch_eligible = []
            
            for subscription in batch:
                # Skip if user already has a notification
                if subscription.user_id in existing_notifications:
                    continue
                    
                # Use the trade model's method to determine accessibility directly
                if trade.is_trade_accessible(subscription.user, subscription):
                    batch_eligible.append(subscription.user_id)
                    continue

                # ALL plans should use the same logic for consistency
                # Get accessible trades for this user based on their subscription plan
                accessible_trades = NotificationManager.get_accessible_trades(subscription.user, subscription)
                
                # Only add user if this trade is in their accessible list
                if (trade.id in accessible_trades['previous_trades'] or 
                    trade.id in accessible_trades['new_trades']):
                    batch_eligible.append(subscription.user_id)
                    logger.info(f"User {subscription.user_id} with {subscription.plan.name} plan is eligible for notification about trade {trade.id}")
                else:
                    logger.info(f"User {subscription.user_id} with {subscription.plan.name} plan is NOT eligible for notification about trade {trade.id}")
            
            eligible_users.extend(batch_eligible)
            end_time = time.time()
            batch_count = len(batch)
            eligible_count = len(batch_eligible)
            logger.info(f"Processed batch of {batch_count} subscriptions in {end_time - start_time:.2f} seconds, {eligible_count} eligible users found")
        
        # Get all eligible user IDs
        logger.info(f"Total eligible users for trade {trade.id}: {len(eligible_users)}")
        return eligible_users

    @staticmethod
    def get_trade_counts(user, subscription):
        """Get current trade counts for the user."""
        try:
            # Get accessible trades
            accessible_trades = NotificationManager.get_accessible_trades(user, subscription)
            
            return {
                'new': len(accessible_trades['new_trades']),
                'previous': len(accessible_trades['previous_trades']),
                'total': len(accessible_trades['new_trades']) + len(accessible_trades['previous_trades'])
            }
            
        except Exception as e:
            logger.error(f"Error getting trade counts: {str(e)}")
            return {'new': 0, 'previous': 0, 'total': 0}

    @staticmethod
    def create_notification(trade, notification_type, short_message, detailed_message=None, batch_size=100):
        """Create notifications for all eligible users"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        start_time = time.time()
        # Get eligible user IDs
        eligible_user_ids = NotificationManager.get_eligible_subscribers(trade, batch_size)
        
        # Update redirectable status for completed trades
        if trade.status == 'COMPLETED':
            try:
                Notification.objects.filter(
                    trade_id=trade.id,
                    trade_status='ACTIVE'
                ).update(is_redirectable=False)
            except DatabaseError as e:
                logger.error(f"Database error updating redirectable status: {e}")
        
        # If no eligible users, return early
        if not eligible_user_ids:
            logger.warning(f"No eligible users found for trade {trade.id}")
            return []
        
        # Prepare common data
        trade_content_type = ContentType.objects.get_for_model(Trade)
        notifications = []
        
        # Create notifications in batches
        for i in range(0, len(eligible_user_ids), batch_size):
            batch_start_time = time.time()
            batch_user_ids = eligible_user_ids[i:i+batch_size]
            
            # Get users in this batch
            batch_users = User.objects.filter(id__in=batch_user_ids)
            
            # Create notification objects (without saving yet)
            batch_notifications = []
            for user in batch_users:
                try:
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
                except Exception as e:
                    logger.error(f"Error creating notification for user {user.id}: {str(e)}")
            
            if not batch_notifications:
                continue
                
            # Use bulk_create for better performance
            try:
                created_notifications = Notification.objects.bulk_create(batch_notifications)
                notifications.extend(created_notifications)
                
                batch_end_time = time.time()
                batch_duration = batch_end_time - batch_start_time
                logger.info(f"Created batch of {len(created_notifications)} notifications in {batch_duration:.2f} seconds")
                
            except Exception as e:
                logger.error(f"Bulk create error: {str(e)}")
        
        end_time = time.time()
        duration = end_time - start_time
        notification_count = len(notifications)
        logger.info(f"Created {notification_count} notifications for trade {trade.id} in {duration:.2f} seconds")
            
        return notifications

    @staticmethod
    def send_websocket_notifications(notifications):
        """Send notifications through websocket"""
        channel_layer = get_channel_layer()
        
        for notification in notifications:
            try:
                # Get the trade object with all related data
                trade = Trade.objects.select_related(
                    'company', 
                    'analysis'
                ).prefetch_related(
                    'history'
                ).get(id=notification.trade_id)
                
                # Format company data with trade
                updated_company = NotificationManager._format_company_with_trade(trade)
                
                # Get user's subscription info
                subscription = Subscription.objects.get(
                    user=notification.recipient,
                    is_active=True,
                    start_date__lte=timezone.now(),
                    end_date__gt=timezone.now()
                )
                
                # Get trade counts
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
                
                logger.info(f"Sending notification {notification.id} to user {notification.recipient.id}")
                async_to_sync(channel_layer.group_send)(
                    f"notification_updates_{notification.recipient.id}",
                    payload
                )
                logger.info(f"Successfully sent notification {notification.id}")
                
            except Exception as e:
                logger.error(f"Error preparing notification payload: {str(e)}")
                continue

@receiver(post_save, sender=Trade)
def handle_trade_updates(sender, instance, created, **kwargs):
    """Handle notifications for trade updates"""
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
            
            # Queue the task to execute asynchronously
            transaction.on_commit(
                lambda: process_trade_notifications.delay(
                    instance.id, 'TRADE', short_message, detailed_message
                )
            )
        else:
            # Trade status update notification
            if instance.status == 'COMPLETED':
                logger.info(f"Queueing notification task for completed trade {instance.id}")
                short_message = f"Trade completed: {instance.company.trading_symbol}"
                detailed_message = f"The trade for {instance.company.trading_symbol} has been completed"
                
                # Queue the task to execute asynchronously
                transaction.on_commit(
                    lambda: process_trade_notifications.delay(
                        instance.id, 'TRADE', short_message, detailed_message
                    )
                )
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