
from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'short_message', 'detailed_message',
            'related_url', 'is_read', 'created_at', 'updated_at', 'trade_data','trade_id','trade_status','is_redirectable'
        ]
        read_only_fields = ['notification_type', 'short_message', 'detailed_message', 'related_url']
