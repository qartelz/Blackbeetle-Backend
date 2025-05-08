from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import uuid

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

