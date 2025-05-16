from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from typing import Dict, List, Optional, Any
import json
from decimal import Decimal
from django.utils import timezone
from urllib.parse import parse_qs
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
import logging
import asyncio
from dataclasses import dataclass
from enum import Enum
import uuid
from django.db import transaction
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Database-specific sync_to_async decorator
db_sync_to_async = sync_to_async(thread_sensitive=True)

class WebSocketCloseCode(Enum):
    """Enumeration of WebSocket close codes for better error handling"""
    NO_TOKEN = 4001
    INVALID_TOKEN = 4002
    AUTH_FAILED = 4003
    UNEXPECTED_AUTH_ERROR = 4004
    NO_SUBSCRIPTION = 4005
    GENERAL_ERROR = 4006
    MAX_RETRIES_EXCEEDED = 4007

@dataclass
class ConnectionConfig:
    """Configuration settings for WebSocket connection"""
    RECONNECT_DELAY: int = 2  # seconds
    MAX_RETRIES: int = 3
    HEARTBEAT_INTERVAL: int = 30  # seconds
    CONNECTION_TIMEOUT: int = 5  # seconds
    CACHE_TIMEOUT: int = 3600  # seconds (1 hour)

class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle Decimal, UUID, and datetime types"""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, uuid.UUID):
            return str(obj)
        # Add datetime handling if needed
        return super().default(obj)

class BaseConsumer(AsyncWebsocketConsumer):
    """
    Base WebSocket consumer with improved connection handling, authentication, 
    and error management.
    """
    
    SUCCESS_MESSAGES = {
        "connected": "Successfully connected.",
        "initial_data": "Initial data loaded successfully.",
        "update": "Update received successfully."
    }
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = None
        self.is_connected = False
        self.connection_retries = 0
        self.config = ConnectionConfig()
        self.heartbeat_task = None
        self.user_group = None
        self._connection_id = str(uuid.uuid4())[:8]  # For tracking connections
        
    async def connect(self) -> None:
        """Handle WebSocket connection with improved reliability"""
        connection_id = self._connection_id
        logger.info(f"[{connection_id}] Connection attempt ({self.connection_retries+1}/{self.config.MAX_RETRIES+1})")
        
        if self.connection_retries >= self.config.MAX_RETRIES:
            logger.warning(f"[{connection_id}] Max retries exceeded")
            await self.close(code=WebSocketCloseCode.MAX_RETRIES_EXCEEDED.value)
            return

        try:
            # First authenticate before accepting the connection
            if not await self._authenticate():
                return  # Auth method handles closing

            # Then accept the connection
            await self.accept()
            logger.info(f"[{connection_id}] Connection accepted for user {self.user.id}")
            
            # Set up user group and start heartbeat
            if await self._setup_user_group():
                self.is_connected = True
                
                # Start heartbeat monitor
                self.heartbeat_task = asyncio.create_task(
                    self._heartbeat_monitor(), 
                    name=f"heartbeat_{self._connection_id}"
                )
                
                # Send success confirmation
                await self.send_success("connected")
                
                # Send initial data
                await self.send_initial_data()
            else:
                await self.close(code=WebSocketCloseCode.GENERAL_ERROR.value)

        except asyncio.TimeoutError:
            logger.error(f"[{connection_id}] Connection timeout")
            await self.close(code=1001)  # Going away
        except Exception as e:
            logger.error(f"[{connection_id}] Connection error: {str(e)}", exc_info=True)
            await self.close(code=WebSocketCloseCode.GENERAL_ERROR.value)
            
            # Implement retry with exponential backoff
            self.connection_retries += 1
            backoff_time = self.config.RECONNECT_DELAY * (2 ** (self.connection_retries - 1))
            await asyncio.sleep(backoff_time)
            await self.connect()

    async def _authenticate(self) -> bool:
        """Authenticate user from JWT token"""
        connection_id = self._connection_id
        try:
            query_string = self.scope.get('query_string', b'').decode('utf-8')
            token = parse_qs(query_string).get('token', [None])[0]
            
            if not token:
                logger.warning(f"[{connection_id}] No token provided")
                await self.close(code=WebSocketCloseCode.NO_TOKEN.value)
                return False

            async with asyncio.timeout(self.config.CONNECTION_TIMEOUT):
                jwt_auth = JWTAuthentication()
                validated_token = await sync_to_async(jwt_auth.get_validated_token)(token)
                self.user = await sync_to_async(jwt_auth.get_user)(validated_token)
            
            if not self.user or not self.user.is_authenticated:
                logger.warning(f"[{connection_id}] Authentication failed")
                await self.close(code=WebSocketCloseCode.AUTH_FAILED.value)
                return False
                
            logger.info(f"[{connection_id}] Authentication successful for user {self.user.id}")
            return True

        except (InvalidToken, TokenError) as e:
            logger.error(f"[{connection_id}] Token validation error: {str(e)}")
            await self.close(code=WebSocketCloseCode.INVALID_TOKEN.value)
            return False
        except Exception as e:
            logger.error(f"[{connection_id}] Unexpected authentication error: {str(e)}", exc_info=True)
            await self.close(code=WebSocketCloseCode.UNEXPECTED_AUTH_ERROR.value)
            return False

    async def _setup_user_group(self) -> bool:
        """Set up user's channel group - override in subclasses"""
        # This should be implemented by subclasses
        raise NotImplementedError("Subclasses must implement _setup_user_group")

    async def send_initial_data(self) -> None:
        """Send initial data - override in subclasses"""
        # This should be implemented by subclasses
        raise NotImplementedError("Subclasses must implement send_initial_data")

    async def _heartbeat_monitor(self) -> None:
        """Send periodic heartbeats to keep connection alive"""
        connection_id = self._connection_id
        logger.info(f"[{connection_id}] Starting heartbeat monitor")
        
        while self.is_connected:
            try:
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat',
                    'timestamp': timezone.now().isoformat()
                }, cls=CustomJSONEncoder))
                
                await asyncio.sleep(self.config.HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                logger.info(f"[{connection_id}] Heartbeat monitor cancelled")
                break
            except Exception as e:
                logger.error(f"[{connection_id}] Heartbeat error: {str(e)}")
                break
                
        logger.info(f"[{connection_id}] Heartbeat monitor stopped")

    async def disconnect(self, close_code: int) -> None:
        """Handle clean disconnection and resource cleanup"""
        connection_id = self._connection_id
        logger.info(f"[{connection_id}] Disconnecting with code {close_code}")
        
        try:
            # Clean up user group
            if self.user_group and self.channel_name:
                await self.channel_layer.group_discard(
                    self.user_group, 
                    self.channel_name
                )
                logger.info(f"[{connection_id}] Removed from group {self.user_group}")
            
            # Clean up state
            self.is_connected = False
            
            # Cancel heartbeat task
            if self.heartbeat_task and not self.heartbeat_task.done():
                self.heartbeat_task.cancel()
                try:
                    await self.heartbeat_task
                except asyncio.CancelledError:
                    pass
                logger.info(f"[{connection_id}] Heartbeat task cancelled")
            
            # Cancel any consumer-specific tasks
            await self._cancel_tasks()
                
        except Exception as e:
            logger.error(f"[{connection_id}] Error during disconnect: {str(e)}", exc_info=True)

    async def _cancel_tasks(self) -> None:
        """Cancel consumer-specific tasks - override in subclasses if needed"""
        pass

    async def receive(self, text_data: str) -> None:
        """Handle incoming messages with validation"""
        connection_id = self._connection_id
        
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'heartbeat_response':
                logger.debug(f"[{connection_id}] Received heartbeat response")
                return
            
            logger.info(f"[{connection_id}] Received message type: {message_type}")
            
            # Process message based on type
            await self._process_message(message_type, data)
            
        except json.JSONDecodeError:
            logger.error(f"[{connection_id}] Invalid JSON received")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid message format'
            }, cls=CustomJSONEncoder))
        except Exception as e:
            logger.error(f"[{connection_id}] Error processing message: {str(e)}", exc_info=True)

    async def _process_message(self, message_type: str, data: Dict) -> None:
        """Process message based on type - override in subclasses"""
        # Default acknowledgment
        await self.send(text_data=json.dumps({
            'type': 'acknowledgment',
            'message': f'Received message of type: {message_type}'
        }, cls=CustomJSONEncoder))

    async def send_success(self, event: str, extra_info: str = None) -> None:
        """Send a success message to the client"""
        message = self.SUCCESS_MESSAGES.get(event, "Operation completed successfully.")
        if extra_info:
            message += f" {extra_info}"
            
        await self.send(text_data=json.dumps({
            "type": "success",
            "event": event,
            "message": message,
            "timestamp": timezone.now().isoformat()
        }, cls=CustomJSONEncoder))

    async def send_error(self, code: int, extra_info: str = None) -> None:
        """Send an error message to the client"""
        try:
            error_code = WebSocketCloseCode(code)
            message = f"Error {code}: {error_code.name}"
        except ValueError:
            message = f"Error {code}"
            
        if extra_info:
            message += f". Details: {extra_info}"
            
        await self.send(text_data=json.dumps({
            "type": "error",
            "code": code,
            "message": message,
            "timestamp": timezone.now().isoformat()
        }, cls=CustomJSONEncoder))

class NotificationConsumer(BaseConsumer):
    """
    WebSocket consumer for handling real-time notifications.
    """
    async def _setup_user_group(self) -> bool:
        """Set up user's notification group"""
        try:
            if self.user:
                # Use a distinct prefix for notification groups
                self.user_group = f"notification_updates_{self.user.id}"
                await self.channel_layer.group_add(
                    self.user_group,
                    self.channel_name
                )
                return True
            return False
        except Exception as e:
            logger.error(f"Error setting up user group: {str(e)}")
            return False


# class NotificationConsumer(BaseConsumer):
#     """
#     WebSocket consumer for handling real-time notifications.
#     """
    
#     def __init__(self, *args: Any, **kwargs: Any) -> None:
#         super().__init__(*args, **kwargs)
    
#     async def _setup_user_group(self) -> bool:
#         """Set up notification group for the user"""
#         connection_id = self._connection_id
#         try:
#             self.user_group = f"notification_updates_{self.user.id}"
#             await self.channel_layer.group_add(self.user_group, self.channel_name)
#             logger.info(f"[{connection_id}] Added to group {self.user_group}")
#             return True
            
#         except Exception as e:
#             logger.error(f"[{connection_id}] Error setting up user group: {str(e)}", exc_info=True)
#             return False

    async def send_initial_data(self) -> None:
        """Send initial notification data"""
        connection_id = self._connection_id
        try:
            if not self.is_connected:
                return
                
            # Get user's unread notifications
            notifications = await self._get_unread_notifications()
            
            data = {
                'notifications': notifications,
                'user_group': self.user_group,
                'connected_at': timezone.now().isoformat(),
                'user_id': self.user.id,
                'connection_id': connection_id
            }
            
            await self.send(text_data=json.dumps({
                'type': 'initial_data',
                'data': data
            }, cls=CustomJSONEncoder))
            
            await self.send_success("initial_data")
            
        except Exception as e:
            logger.error(f"[{connection_id}] Error sending initial data: {str(e)}", exc_info=True)
            if self.is_connected:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': "Failed to load initial data"
                }, cls=CustomJSONEncoder))

    @db_sync_to_async
    def _get_unread_notifications(self):
        """Get user's unread notifications"""
        from .models import Notification
        
        notifications = Notification.objects.filter(
            recipient=self.user,
            is_read=False
        ).order_by('-created_at')[:50]  # Limit to last 50 unread notifications
        
        return [
            {
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
            for notif in notifications
        ]

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
            
            # Log the notification details
            logger.info(f"[{connection_id}] Notification type: {message_type}, trade_id: {message.get('trade_id')}")
            
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
        else:
            await super()._process_message(message_type, data)

    @db_sync_to_async
    def _mark_notification_read(self, notification_id):
        """Mark a notification as read"""
        from .models import Notification
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient=self.user
            )
            notification.is_read = True
            notification.save()
            
            return {
                'id': str(notification.id),
                'is_read': True
            }
        except Notification.DoesNotExist:
            logger.warning(f"Notification {notification_id} not found for user {self.user.id}")
            return None