from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import uuid
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.trades.models import Trade
from datetime import timedelta
import logging
import traceback

User = get_user_model()

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('TRADE', 'Trade Update'),
        ('ANALYSIS', 'Analysis Update'),
        ('PRICE', 'Price Update'),
        ('RISK', 'Risk Update'),
        ('INSIGHT', 'Trade Insight'),
    )
    
    # id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey('users.User', on_delete=models.CASCADE)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    short_message = models.CharField(max_length=255)
    detailed_message = models.TextField(null=True, blank=True)
    related_url = models.CharField(max_length=255, null=True, blank=True)

    trade_data = models.JSONField(null=True, blank=True)
    trade_id =models.PositiveBigIntegerField(null=True, blank=True)
    trade_status = models.CharField(max_length=255, null=True, blank=True)
    is_redirectable = models.BooleanField(default=True)
    

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['created_at']),
            models.Index(fields=['notification_type']),
        ]


# class BaseModel(models.Model):
#     # id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     created_at = models.DateTimeField(auto_now_add=True, db_index=True)
#     updated_at = models.DateTimeField(auto_now=True)
#     is_active = models.BooleanField(default=True, db_index=True)

#     class Meta:
#         abstract = True
#         ordering = ["-created_at"]
#         get_latest_by = "created_at"

# class Notification(BaseModel):
#     NOTIFICATION_TYPES = (
#         ('TRADE', 'Trade Update'),
#         ('SUBSCRIPTION', 'Subscription'),
#         ('ORDER', 'Order'),
#         ('SYSTEM', 'System'),
#         ('ANALYSIS', 'Analysis'),
#         ('PAYMENT', 'Payment'),
#     )
 
#     recipient = models.ForeignKey('users.User', on_delete=models.CASCADE)
#     notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
#     is_read = models.BooleanField(default=False)
    
#     # Generic foreign key to handle different notification sources
#     content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
#     object_id = models.UUIDField()
#     content_object = GenericForeignKey('content_type', 'object_id')

#     # Additional fields for quick access
#     short_message = models.CharField(max_length=255)
#     related_url = models.URLField(null=True, blank=True)
#     trade_data = models.JSONField(null=True, blank=True)

#     class Meta:
#         indexes = [
#             models.Index(fields=['recipient', 'is_read']),
#             models.Index(fields=['created_at']),
#             models.Index(fields=['notification_type']),
#         ]

#     def save(self, *args, **kwargs):
#         # Auto-generate short message if not provided
#         if not self.short_message:
#             self.short_message = self.generate_short_message()
#         super().save(*args, **kwargs)
    
#     def generate_short_message(self):
#         if self.notification_type == 'SUBSCRIPTION':
#             return f"Subscription update: {self.content_object.plan.name}"
#         elif self.notification_type == 'ORDER':
#             return f"Order status: {self.content_object.status}"
#         # Add other types as needed
#         return "New notification"

#     @property
#     def notification_icon(self):
#         icons = {
#             'TRADE': '📈',
#             'SUBSCRIPTION': '🔄',
#             'ORDER': '📦',
#             'PAYMENT': '💳',
#             'SYSTEM': '🔔',
#             'ANALYSIS': '📊'
#         }
#         return icons.get(self.notification_type, '🔔')


# class Notification(BaseModel):
#     NOTIFICATION_TYPES = (
#         ('INFO', 'Information'),
#         ('WARNING', 'Warning'),
#         ('ERROR', 'Error'),
#         ('SUCCESS', 'Success'),
#     )

#     recipient = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='notifications')
#     title = models.CharField(max_length=255)
#     message = models.TextField()
#     notification_type = models.CharField(max_length=10, choices=NOTIFICATION_TYPES, default='INFO')
#     is_read = models.BooleanField(default=False)
    
#     content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
#     object_id = models.UUIDField(null=True, blank=True)
#     content_object = GenericForeignKey('content_type', 'object_id')
#     institution = models.ForeignKey('institutions.Institution', on_delete=models.CASCADE, null=True, blank=True, related_name='institution_notifications')

#     class Meta(BaseModel.Meta):
#         ordering = ['-created_at']

#     def __str__(self):
#         return f"{self.get_notification_type_display()} for {self.recipient}: {self.title}"

class NotificationPreference(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    enable_trade_updates = models.BooleanField(default=True)
    enable_realtime_updates = models.BooleanField(default=True)
    enable_email_notifications = models.BooleanField(default=True)
    enable_push_notifications = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification preferences for {self.user.email}"

class TradeNotification(models.Model):
    class NotificationType(models.TextChoices):
        TRADE_UPDATE = 'TRADE_UPDATE', 'Trade Update'
        TRADE_COMPLETED = 'TRADE_COMPLETED', 'Trade Completed'
        TRADE_CANCELLED = 'TRADE_CANCELLED', 'Trade Cancelled'
        WARZONE_UPDATE = 'WARZONE_UPDATE', 'Warzone Update'

    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        NORMAL = 'NORMAL', 'Normal'
        HIGH = 'HIGH', 'High'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='trade_notifications'
    )
    trade = models.ForeignKey(
        Trade,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices
    )
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.NORMAL
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', 'created_at']),
            models.Index(fields=['trade', 'notification_type']),
        ]

    def __str__(self):
        return f"{self.notification_type} notification for {self.user.email}"

    @classmethod
    def create_trade_notification(cls, user, trade, notification_type, message, priority=Priority.NORMAL):
        """
        Create a new trade notification and handle delivery based on user preferences.
        """
        if not hasattr(user, 'notification_preferences'):
            return None

        prefs = user.notification_preferences
        if not prefs.enable_trade_updates:
            return None

        notification = cls.objects.create(
            user=user,
            trade=trade,
            notification_type=notification_type,
            message=message,
            priority=priority
        )

        # Handle real-time updates
        if prefs.enable_realtime_updates:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"trade_updates_{user.id}",
                {
                    "type": "notification",
                    "data": {
                        "id": notification.id,
                        "type": notification.notification_type,
                        "message": notification.message,
                        "priority": notification.priority,
                        "created_at": notification.created_at.isoformat(),
                        "trade_id": trade.id
                    }
                }
            )

        # Handle email notifications
        if prefs.enable_email_notifications:
            from django.core.mail import send_mail
            send_mail(
                subject=f"Trade Update: {trade.company.trading_symbol}",
                message=message,
                from_email=None,  # Use default from email
                recipient_list=[user.email],
                fail_silently=True
            )

        return notification

@staticmethod
def create_trade_notification(trade: Trade, action: str = "updated"):
    try:
        # Add a time threshold to prevent duplicates (e.g., 5 seconds)
        recent_notification_threshold = timezone.now() - timedelta(seconds=5)

        subscriptions = Subscription.objects.filter(
            is_active=True,
            end_date__gt=timezone.now()
        ).select_related('user', 'plan')

        for subscription in subscriptions:
            if TradeSignalHandler.should_send_trade_update(subscription.user, trade, subscription):
                # Check for recent notifications for this trade and user
                recent_notification_exists = TradeNotification.objects.filter(
                    user=subscription.user,
                    trade=trade,
                    created_at__gte=recent_notification_threshold
                ).exists()

                if not recent_notification_exists:
                    notification_type = (
                        TradeNotification.NotificationType.TRADE_COMPLETED 
                        if trade.status == 'COMPLETED' 
                        else TradeNotification.NotificationType.TRADE_UPDATE
                    )
                    
                    message = (
                        f"Trade completed for {trade.company.trading_symbol}"
                        if trade.status == 'COMPLETED'
                        else f"Trade update for {trade.company.trading_symbol}: {action}"
                    )
                    
                    TradeNotification.create_trade_notification(
                        user=subscription.user,
                        trade=trade,
                        notification_type=notification_type,
                        message=message,
                        priority=TradeNotification.Priority.HIGH if trade.status == 'ACTIVE' else TradeNotification.Priority.NORMAL
                    )
                    logger.info(f"Created notification for user {subscription.user.id} for trade {trade.id}")
                else:
                    logger.info(f"Skipped duplicate notification for user {subscription.user.id} for trade {trade.id}")

    except Exception as e:
        logger.error(f"Error creating trade notifications: {str(e)}")
        logger.error(traceback.format_exc())

