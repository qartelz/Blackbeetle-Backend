from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
import json
import logging

logger = logging.getLogger(__name__)

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