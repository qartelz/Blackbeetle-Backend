from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task
def process_trade_notifications(trade_id, notification_type, short_message, detailed_message=None):
    """Process notifications for trade updates"""
    from .unified_notifications import UnifiedTradeNotificationManager
    
    logger.info(f"Processing trade notification task - Trade ID: {trade_id}, Type: {notification_type}")
    
    try:
        # Use the unified notification manager
        UnifiedTradeNotificationManager.process_trade_notification(
            trade_id, notification_type, short_message, detailed_message
        )
        logger.info(f"Successfully processed notification for trade {trade_id}")
        
    except Exception as e:
        logger.error(f"Error processing notification for trade {trade_id}: {str(e)}", exc_info=True)


# from celery import shared_task
# from django.contrib.contenttypes.models import ContentType
# from django.db import transaction
# from django.utils import timezone
# from django.db.models import Q
# from django.db import DatabaseError
# from django.contrib.auth import get_user_model
# from channels.layers import get_channel_layer
# from asgiref.sync import async_to_sync
# from apps.trades.models import Trade
# from apps.subscriptions.models import Subscription
# from .models import Notification
# import logging
# import time

# logger = logging.getLogger(__name__)

# # Constants for batching
# BATCH_SIZE = 100  # Process 100 notifications at a time

# User = get_user_model()

# @shared_task
# def process_trade_notifications(trade_id, notification_type, short_message, detailed_message=None):
#     """
#     Process notifications for a trade in an efficient, batched manner.
#     This task handles filtering eligible users, creating notifications, and sending them.
#     """
#     logger.info(f"Starting notification processing for trade {trade_id}")
#     start_time = time.time()
    
#     try:
#         # Get the trade with related data
#         trade = Trade.objects.select_related('company').get(id=trade_id)
#         trade_content_type = ContentType.objects.get_for_model(Trade)
        
#         # Skip if trade is PENDING
#         if trade.status == 'PENDING':
#             logger.info(f"Skipping notifications for PENDING trade {trade_id}")
#             return
        
#         logger.info(f"Processing notifications for trade {trade_id} ({trade.company.trading_symbol}), status: {trade.status}, plan_type: {trade.plan_type}, created_at: {trade.created_at}")
        
#         # Get eligible plan levels
#         from apps.notifications.signals import NotificationManager
#         eligible_plans = NotificationManager.get_plan_levels(trade.plan_type)
#         eligible_plans_with_premium = eligible_plans + ['SUPER_PREMIUM', 'FREE_TRIAL']
        
#         logger.info(f"Eligible plans for trade {trade_id}: {eligible_plans_with_premium}")
        
#         # Get active subscriptions more efficiently using a single query
#         active_subscriptions = Subscription.objects.filter(
#             plan__name__in=eligible_plans_with_premium,
#             is_active=True,
#             start_date__lte=timezone.now(),
#             end_date__gt=timezone.now()
#         ).select_related('user', 'plan')
        
#         # Get existing notifications to avoid duplicates
#         existing_notifications = set(Notification.objects.filter(
#             trade_id=trade_id,
#             notification_type=notification_type
#         ).values_list('recipient_id', flat=True))
        
#         logger.info(f"Found {active_subscriptions.count()} potentially eligible subscriptions for trade {trade_id}")
#         logger.info(f"Found {len(existing_notifications)} existing notifications for trade {trade_id}")
        
#         # Update redirectable status for completed trades
#         if trade.status == 'COMPLETED':
#             logger.info(f"Trade {trade_id} is completed, updating old notification status")
#             try:
#                 updated_count = Notification.objects.filter(
#                     trade_id=trade_id,
#                     trade_status='ACTIVE'
#                 ).update(is_redirectable=False)
#                 logger.info(f"Updated redirectable status for {updated_count} notifications")
#             except DatabaseError as e:
#                 logger.error(f"Database error updating redirectable status: {e}")
        
#         # Process subscriptions in batches to determine eligible users
#         subscription_count = active_subscriptions.count()
#         eligible_users = []
#         not_eligible_count = 0
        
#         # For previous trades, we need to check more carefully
#         is_previous_trade = False
        
#         for i in range(0, subscription_count, BATCH_SIZE):
#             batch = active_subscriptions[i:i+BATCH_SIZE]
            
#             # We'll collect user IDs from this batch who are eligible
#             batch_eligible_users = []
#             batch_not_eligible = 0
            
#             for subscription in batch:
#                 # Skip if user already has a notification for this trade/type
#                 if subscription.user_id in existing_notifications:
#                     continue
                
#                 # Check if this is a previous trade for this subscription
#                 if trade.created_at < subscription.start_date:
#                     is_previous_trade = True
                
#                 # Use direct trade accessibility check - with more detailed logging
#                 try:
#                     # First try the most direct method
#                     if trade.is_trade_accessible(subscription.user, subscription):
#                         batch_eligible_users.append(subscription.user_id)
#                         logger.info(f"User {subscription.user_id} with {subscription.plan.name} plan is eligible for notification about trade {trade_id}")
#                     else:
#                         # If not directly accessible, try to check accessible_trades 
#                         # (especially important for previous trades)
#                         accessible_trades = NotificationManager.get_accessible_trades(subscription.user, subscription)
                        
#                         if (trade.id in accessible_trades['previous_trades'] or 
#                             trade.id in accessible_trades['new_trades']):
#                             batch_eligible_users.append(subscription.user_id)
#                             logger.info(f"User {subscription.user_id} with {subscription.plan.name} plan is eligible for notification via accessible_trades about trade {trade_id}")
#                         else:
#                             batch_not_eligible += 1
#                             logger.info(f"User {subscription.user_id} with {subscription.plan.name} plan is NOT eligible for notification about trade {trade_id}")
#                 except Exception as e:
#                     logger.error(f"Error checking eligibility for user {subscription.user_id}: {str(e)}")
#                     # In case of error, we'll try the accessible_trades method as a fallback
#                     try:
#                         accessible_trades = NotificationManager.get_accessible_trades(subscription.user, subscription)
                        
#                         if (trade.id in accessible_trades['previous_trades'] or 
#                             trade.id in accessible_trades['new_trades']):
#                             batch_eligible_users.append(subscription.user_id)
#                             logger.info(f"User {subscription.user_id} eligible via fallback method for trade {trade_id}")
#                     except Exception as fallback_error:
#                         logger.error(f"Fallback eligibility check failed for user {subscription.user_id}: {str(fallback_error)}")
            
#             eligible_users.extend(batch_eligible_users)
#             not_eligible_count += batch_not_eligible
            
#             logger.info(f"Batch {i//BATCH_SIZE + 1}: Found {len(batch_eligible_users)} eligible users and {batch_not_eligible} non-eligible users")
        
#         # Early return if no eligible users
#         if not eligible_users:
#             logger.warning(f"No eligible users found for trade {trade_id} notifications (checked {subscription_count} users, {not_eligible_count} were not eligible)")
#             return []
        
#         # Create notifications in batches
#         logger.info(f"Creating notifications for {len(eligible_users)} eligible users")
#         notifications = []
#         notification_count = 0
        
#         for i in range(0, len(eligible_users), BATCH_SIZE):
#             batch_user_ids = eligible_users[i:i+BATCH_SIZE]
#             batch_users = User.objects.filter(id__in=batch_user_ids)
            
#             batch_notifications = []
#             for user in batch_users:
#                 notification = Notification(
#                     recipient=user,
#                     notification_type=notification_type,
#                     content_type=trade_content_type,
#                     object_id=trade.id,
#                     short_message=short_message,
#                     detailed_message=detailed_message,
#                     trade_status=trade.status,
#                     is_redirectable=True,
#                     trade_id=trade.id,
#                     related_url=f"/trades/{trade.id}"
#                 )
#                 batch_notifications.append(notification)
            
#             # Use bulk_create for efficiency
#             created_batch = Notification.objects.bulk_create(batch_notifications)
#             notification_count += len(created_batch)
#             notifications.extend(created_batch)
            
#             logger.info(f"Created batch of {len(created_batch)} notifications for trade {trade_id}")
        
#         end_time = time.time()
#         logger.info(f"Created {notification_count} notifications for trade {trade_id} in {end_time - start_time:.2f} seconds")
        
#         # Send websocket notifications (but don't wait for this to complete)
#         if notification_count > 0:
#             send_websocket_notifications.delay([n.id for n in notifications])
        
#         return notification_count
        
#     except Trade.DoesNotExist:
#         logger.error(f"Trade {trade_id} not found")
#     except Exception as e:
#         logger.error(f"Error processing notifications for trade {trade_id}: {str(e)}", exc_info=True)
    
#     return 0

# @shared_task
# def send_websocket_notifications(notification_ids, batch_size=20):
#     """Send websocket notifications in batches"""
#     logger.info(f"Starting websocket notifications for {len(notification_ids)} notifications")
#     start_time = time.time()
    
#     channel_layer = get_channel_layer()
#     sent_count = 0
    
#     # Process in batches to avoid overloading the system
#     for i in range(0, len(notification_ids), batch_size):
#         batch_ids = notification_ids[i:i+batch_size]
        
#         # Get notifications with all related data in one efficient query
#         notifications = Notification.objects.filter(
#             id__in=batch_ids
#         ).select_related('recipient')
        
#         logger.info(f"Processing batch of {len(notifications)} notifications")
        
#         for notification in notifications:
#             try:
#                 # Get the trade object with all related data (with optimized queries)
#                 trade = Trade.objects.select_related(
#                     'company', 
#                     'analysis'
#                 ).prefetch_related(
#                     'history'
#                 ).get(id=notification.trade_id)
                
#                 # Get user's subscription efficiently
#                 subscription = Subscription.objects.filter(
#                     user=notification.recipient,
#                     is_active=True,
#                     start_date__lte=timezone.now(),
#                     end_date__gt=timezone.now()
#                 ).select_related('plan').first()
                
#                 if not subscription:
#                     logger.warning(f"No active subscription found for user {notification.recipient.id}, skipping notification {notification.id}")
#                     continue
                
#                 # Get formatted data
#                 from apps.notifications.signals import NotificationManager
#                 updated_company = NotificationManager._format_company_with_trade(trade)
#                 trade_counts = NotificationManager.get_trade_counts(notification.recipient, subscription)
                
#                 # Get plan limits
#                 plan_limits = {
#                     'BASIC': {'new': 6, 'previous': 6, 'total': 12},
#                     'PREMIUM': {'new': 9, 'previous': 6, 'total': 15},
#                     'SUPER_PREMIUM': {'new': None, 'previous': 6, 'total': None},
#                     'FREE_TRIAL': {'new': None, 'previous': 6, 'total': None}
#                 }
                
#                 limits = plan_limits.get(subscription.plan.name, {'new': None, 'previous': 6})
                
#                 # Calculate remaining slots
#                 remaining = {
#                     'new': None if limits['new'] is None else max(0, limits['new'] - trade_counts['new']),
#                     'previous': None if limits['previous'] is None else max(0, limits['previous'] - trade_counts['previous']),
#                     'total': None if limits['total'] is None else max(0, limits['total'] - trade_counts['total'])
#                 }
                
#                 # Determine message type based on trade status
#                 message_type = "trade_completed" if notification.trade_status == 'COMPLETED' else "trade_update"
                
#                 payload = {
#                     'type': 'new_notification',
#                     'message': {
#                         'id': str(notification.id),
#                         'type': notification.notification_type,
#                         'message_type': message_type,
#                         'short_message': notification.short_message,
#                         'detailed_message': notification.detailed_message,
#                         'created_at': notification.created_at.isoformat(),
#                         'related_url': notification.related_url,
#                         'trade_status': notification.trade_status,
#                         'trade_id': notification.trade_id,
#                         'is_redirectable': notification.is_redirectable,
#                         'data': {
#                             'updated_company': updated_company,
#                             'subscription': {
#                                 'plan': subscription.plan.name,
#                                 'start_date': subscription.start_date.isoformat(),
#                                 'end_date': subscription.end_date.isoformat(),
#                                 'limits': limits,
#                                 'current': trade_counts,
#                                 'remaining': remaining
#                             }
#                         }
#                     }
#                 }
                
#                 # Try multiple channel formats to ensure compatibility
#                 user_id = notification.recipient.id
                
#                 # Original channel name
#                 channel_name = f"notification_updates_{user_id}"
#                 logger.info(f"Sending notification {notification.id} to channel {channel_name}")
                
#                 try:
#                     async_to_sync(channel_layer.group_send)(
#                         channel_name,
#                         payload
#                     )
#                     sent_count += 1
#                 except Exception as channel_error:
#                     logger.error(f"Error sending to channel {channel_name}: {str(channel_error)}")
                    
#                     # Try alternative channel format if the app uses a different format
#                     alt_channel_name = f"user_{user_id}_notifications"
#                     logger.info(f"Trying alternative channel {alt_channel_name}")
                    
#                     try:
#                         async_to_sync(channel_layer.group_send)(
#                             alt_channel_name,
#                             payload
#                         )
#                         sent_count += 1
#                         logger.info(f"Successfully sent to alternative channel {alt_channel_name}")
#                     except Exception as alt_channel_error:
#                         logger.error(f"Error sending to alternative channel {alt_channel_name}: {str(alt_channel_error)}")
                
#             except Trade.DoesNotExist:
#                 logger.error(f"Trade {notification.trade_id} not found for notification {notification.id}")
#             except Exception as e:
#                 logger.error(f"Error sending websocket notification {notification.id}: {str(e)}", exc_info=True)
        
#         # Small sleep between batches to avoid overwhelming the websocket server
#         if i + batch_size < len(notification_ids):
#             time.sleep(0.1)
    
#     end_time = time.time()
#     logger.info(f"Sent {sent_count} websocket notifications in {end_time - start_time:.2f} seconds")
#     return sent_count 