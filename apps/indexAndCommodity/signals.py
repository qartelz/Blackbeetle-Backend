from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from decimal import Decimal
from .models import Trade, TradeHistory,Analysis,Insight
from apps.notifications.models import Notification
from django.db import DatabaseError
import logging

logger = logging.getLogger(__name__)

class NotificationManager:
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
    def get_eligible_subscribers(plan_type):
        """Get users with active subscriptions for given plan type"""
        from apps.subscriptions.models import Subscription
        today = timezone.now().date()
        
        return Subscription.objects.filter(
            end_date__gte=today,
            is_active=True,
            plan__name__in=NotificationManager.get_plan_levels(plan_type)
        ).values_list('user_id', flat=True).distinct()

    @staticmethod
    def create_notification(trade, notification_type, short_message, detailed_message=None):
        """Create notifications for all eligible users"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        eligible_users = User.objects.filter(
            id__in=NotificationManager.get_eligible_subscribers(trade.plan_type)
        )
        
        trade_content_type = ContentType.objects.get_for_model(Trade)
        # trade_data = {
        #     'company': trade.company.trading_symbol,
        #     'plan_type': trade.plan_type,
        #     'status': trade.status,
        #     'instrumentName': trade.company.instrument_type,
        #     'trade_id': str(trade.id),
        #     'category': 'stock',
        # }
        trade_data = {
            'company': trade.index_and_commodity.tradingSymbol,
            'plan_type': trade.plan_type,
            'status': trade.status,
            'instrumentName': trade.index_and_commodity.instrumentName,
            'trade_id': str(trade.id),
            'category': 'index_and_commodity',
        }
        if trade.status == 'COMPLETED':
            try:
                Notification.objects.filter(
                    trade_id=trade.id,
                    trade_status='ACTIVE'
                ).update(is_redirectable=False)
            except DatabaseError as e:
                # Log the error or handle it as needed
                print(f"Database error occurred: {e}")
        
        notifications = []
        for user in eligible_users:
            notification = Notification.objects.create(
                recipient=user,
                notification_type=notification_type,
                content_type=trade_content_type,
                object_id=trade.id,
                short_message=short_message,
                trade_status=trade.status,
                trade_id=trade.id,
                is_redirectable=True,
                detailed_message=detailed_message,
                related_url=f"/trades/{trade.id}",
                trade_data=trade_data
            )
            notifications.append(notification)
            
        return notifications

    @staticmethod
    def send_websocket_notifications(notifications):
        """Send notifications through websocket"""
        channel_layer = get_channel_layer()
        print('send_websocket_notifications>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>')
        
        for notification in notifications:
            payload = {
                'type': 'new_notification',
                'message': {
                    'id': str(notification.id),
                    'type': notification.notification_type,
                    'short_message': notification.short_message,
                    'detailed_message': notification.detailed_message,
                    'trade_status':notification.trade_status,
                    'trade_id':notification.trade_id,
                    'is_redirectable':notification.is_redirectable,
                    'created_at': notification.created_at.isoformat(),
                    'related_url': notification.related_url,
                    'trade_data': notification.trade_data
                }
            }
            print('payload>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>')
            
            async_to_sync(channel_layer.group_send)(
                f"notification_updates_{notification.recipient.id}",
                payload
            )

@receiver(post_save, sender=Trade)
def handle_trade_updates(sender, instance, created, **kwargs):
    """Handle all trade-related notifications"""
    
    # Skip notifications for PENDING trades
    if instance.status == 'PENDING':
        logger.info(f"Skipping notification for PENDING trade {instance.id}")
        return
    
    notifications = []
    
    # Skip if no relevant fields changed
    if not any([
        instance.tracker.has_changed('status'),
        instance.tracker.has_changed('image'),
        instance.tracker.has_changed('warzone')
    ]):
        return
        
    # Status change notifications
    if instance.tracker.has_changed('status'):
        if instance.status == 'ACTIVE':
            notifications.extend(
                NotificationManager.create_notification(
                    instance,
                    'TRADE',
                    f"New trade activated: {instance.index_and_commodity.tradingSymbol}",
                    f"A new trade has been activated for {instance.index_and_commodity.tradingSymbol}"
                )
            )
        elif instance.status == 'COMPLETED':
            notifications.extend(
                NotificationManager.create_notification(
                    instance,
                    'TRADE',
                    f"Trade completed: {instance.index_and_commodity.tradingSymbol}",
                    f"Trade for {instance.index_and_commodity.tradingSymbol} has been completed"
                )
            )
    
    # Image update notifications (only for active trades)
    if instance.status == 'ACTIVE' and instance.tracker.has_changed('image'):
        notifications.extend(
            NotificationManager.create_notification(
                instance,
                'TRADE',
                f"Chart updated: {instance.index_and_commodity.tradingSymbol}",
                "Technical analysis chart has been updated"
            )
        )
    
    # Warzone update notifications (only for active trades)
    if instance.status == 'ACTIVE' and instance.tracker.has_changed('warzone'):
        notifications.extend(
            NotificationManager.create_notification(
                instance,
                'RISK',
                f"Risk level updated: {instance.index_and_commodity.tradingSymbol}",
                f"Risk level has changed to {instance.warzone}"
            )
        )
    
    # Send all notifications
    if notifications:
        transaction.on_commit(
            lambda: NotificationManager.send_websocket_notifications(notifications)
        )

@receiver(post_save, sender=TradeHistory)
def handle_trade_history_updates(sender, instance, created, **kwargs):
    """Handle notifications for price target updates"""
    if created and instance.trade.status == 'ACTIVE':
        notifications = NotificationManager.create_notification(
            instance.trade,
            'PRICE',
            f"Price targets updated: {instance.trade.index_and_commodity.tradingSymbol}",
            (f"New price targets set - Buy: {instance.buy}, "
             f"Target: {instance.target}, SL: {instance.sl}")
        )
        
        if notifications:
            transaction.on_commit(
                lambda: NotificationManager.send_websocket_notifications(notifications)
            )

@receiver(post_save, sender=Analysis)
def handle_analysis_updates(sender, instance, created, **kwargs):
    """Handle notifications for analysis updates"""
    if instance.trade.status == 'ACTIVE':
        action = "created" if created else "updated"
        notifications = NotificationManager.create_notification(
            instance.trade,
            'ANALYSIS',
            f"Analysis {action}: {instance.trade.index_and_commodity.tradingSymbol}",
            f"Trade analysis has been {action}"
        )
        
        if notifications:
            transaction.on_commit(
                lambda: NotificationManager.send_websocket_notifications(notifications)
            )

@receiver(post_save, sender=Insight)
def handle_insight_updates(sender, instance, created, **kwargs):
    """Handle notifications for insight updates"""
    if instance.trade.status == 'COMPLETED':
        action = "created" if created else "updated"
        
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
        
        notifications = NotificationManager.create_notification(
            instance.trade,
            'INSIGHT',
            f"Trade insight {action}: {instance.trade.index_and_commodity.tradingSymbol}",
            f"Trade insight {action} with updates to {field_text}"
        )
        
        if notifications:
            transaction.on_commit(
                lambda: NotificationManager.send_websocket_notifications(notifications)
            )





# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from django.utils import timezone
# from django.db.models import Q
# from channels.layers import get_channel_layer
# from asgiref.sync import async_to_sync
# from typing import List

# from apps.notifications.models import Notification
# from apps.subscriptions.models import Subscription
# from .models import Trade
# from django.contrib.contenttypes.models import ContentType
# from django.db import transaction

# class TradeUpdateManager:
#     @staticmethod
#     def get_plan_levels(plan_type: str) -> List[str]:
#         """
#         Returns list of plan levels that can access trades of given plan type
#         Implements hierarchical access control
#         """
#         plan_access = {
#             'BASIC': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM'],
#             'PREMIUM': ['PREMIUM', 'SUPER_PREMIUM'],
#             'SUPER_PREMIUM': ['SUPER_PREMIUM']
#         }
#         return plan_access.get(plan_type, [])

# @receiver(post_save, sender=Trade)
# def handle_trade_update(sender, instance, created, **kwargs):
#     if not created and instance.status in ["ACTIVE", "COMPLETED"]:
#         # Check if status has changed
#         if hasattr(instance, 'tracker') and instance.tracker.has_changed('status'):
#             transaction.on_commit(lambda: process_trade_update(instance))

# def process_trade_update(trade):
#     print('---------------------------------------------------notifications------------------------------------------')
#     notifications = create_trade_notifications(trade)
#     if notifications:
#         send_websocket_notifications(trade, notifications)


# def create_trade_notifications(trade) -> List[Notification]:
#     today = timezone.now().date()
    
#     # Get distinct users with active subscriptions
#     user_ids = Subscription.objects.filter(
#         Q(end_date__gte=today) &
#         Q(is_active=True) &
#         Q(plan__name__in=TradeUpdateManager.get_plan_levels(trade.plan_type))
#     ).values_list('user_id', flat=True).distinct()

#     if not user_ids:
#         return []
#     print(user_ids,'---------------------------------------------------user_ids------------------------------------------')

#     short_message = f"New trade alert for {trade.index_and_commodity}" if trade.status == "ACTIVE" else f"Trade completed: {trade.index_and_commodity}"
#     related_url = f"/trades/{trade.id}"
#     trade_content_type = ContentType.objects.get_for_model(Trade)
#     trade_data = {
#                     'company': trade.index_and_commodity.tradingSymbol,
#                     'plan_type': trade.plan_type,
#                     'status': trade.status,
#                     'instrumentName': trade.index_and_commodity.instrumentName,
#                     'trade_id': trade.id,
#                     'category': 'index_and_commodity',
#                 }

#     print(trade_content_type,'---------------------------------------------------trade_content_type------------------------------------------')

#     # Fetch users in one query
#     from django.contrib.auth import get_user_model
#     User = get_user_model()
#     users = User.objects.filter(id__in=user_ids)

#     notifications = Notification.objects.bulk_create([
#         Notification(
#             recipient=user,
#             notification_type='TRADE',
#             content_type=trade_content_type,
#             object_id=trade.id,
#             short_message=short_message,
#             related_url=related_url,
#             trade_data=trade_data
#         ) for user in users
#     ])

#     return notifications

# def send_websocket_notifications(trade, notifications: List[Notification]):
#     """
#     Sends websocket notifications to all recipients.
#     Uses the notification objects to ensure consistency with DB records.
#     """
#     channel_layer = get_channel_layer()

#     # Group notifications by recipient for efficient websocket messaging
#     for notification in notifications:
#         # Prepare notification payload
#         payload = {
#             'type': 'new_notification',
#             'message': {
#                 'id': str(notification.id),  # Assuming UUID field
#                 'type': notification.notification_type,
#                 'short_message': notification.short_message,
#                 'created_at': notification.created_at.isoformat(),
#                 'icon': notification.notification_icon,
#                 'related_url': notification.related_url,
#                'trade_data': {
#                     'company': trade.index_and_commodity.tradingSymbol,
#                     'plan_type': trade.plan_type,
#                     'status': trade.status,
#                     'instrumentName': trade.index_and_commodity.instrumentName,
#                     'trade_id': trade.id,
#                     'category': 'index_and_commodity',
#                 }
#             }
#         }

#         # Send to user's notification channel
#         async_to_sync(channel_layer.group_send)(
#             f"notification_updates_{notification.recipient.id}",
#             payload
#         )