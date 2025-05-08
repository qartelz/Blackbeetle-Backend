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

logger = logging.getLogger(__name__)

class WebSocketCloseCode(Enum):
    """Enumeration of WebSocket close codes for better error handling"""
    NO_TOKEN = 4001
    INVALID_TOKEN = 4002
    AUTH_FAILED = 4003
    UNEXPECTED_AUTH_ERROR = 4004
    GROUP_SETUP_ERROR = 4006

@dataclass
class ConnectionConfig:
    """Configuration settings for WebSocket connection"""
    RECONNECT_DELAY: int = 5  # seconds
    MAX_RETRIES: int = 3
    HEARTBEAT_INTERVAL: int = 30  # seconds
    CONNECTION_TIMEOUT: int = 10  # seconds

class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle Decimal and UUID types"""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)

class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for handling real-time notifications with improved error handling
    and connection management.
    """
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = None
        self.is_connected = False
        self.connection_retries = 0
        self.config = ConnectionConfig()
        self.heartbeat_task = None

    async def connect(self) -> None:
        """Handles initial WebSocket connection with enhanced error handling and monitoring"""
        try:
            if not await self._authenticate():
                return

            self.is_connected = True
            await self.accept()
            
            if await self._setup_user_group():
                self.heartbeat_task = asyncio.create_task(
                    self._heartbeat_monitor(), 
                    name=f"heartbeat_{self.channel_name}"
                )
                await self.send_initial_data()
            
        except asyncio.TimeoutError:
            logger.error("Connection timeout")
            await self.close(code=1001)  # Going away
        except Exception as e:
            logger.error(f"Connection error: {str(e)}", exc_info=True)
            await self.close()
            if self.connection_retries < self.config.MAX_RETRIES:
                self.connection_retries += 1
                await asyncio.sleep(self.config.RECONNECT_DELAY)
                await self.connect()

    async def _authenticate(self) -> bool:
        """Enhanced authentication with better error handling and logging"""
        try:
            query_string = self.scope.get('query_string', b'').decode('utf-8')
            token = parse_qs(query_string).get('token', [None])[0]
            
            if not token:
                logger.warning("No token provided in connection request")
                await self.close(code=WebSocketCloseCode.NO_TOKEN.value)
                return False

            async with asyncio.timeout(self.config.CONNECTION_TIMEOUT):
                jwt_auth = JWTAuthentication()
                validated_token = jwt_auth.get_validated_token(token)
                self.user = await sync_to_async(jwt_auth.get_user)(validated_token)
            
            if not self.user or not self.user.is_authenticated:
                logger.warning(f"Authentication failed for user")
                await self.close(code=WebSocketCloseCode.AUTH_FAILED.value)
                return False
                
            return True

        except (InvalidToken, TokenError) as e:
            logger.error(f"Token validation error: {str(e)}")
            await self.close(code=WebSocketCloseCode.INVALID_TOKEN.value)
            return False
        except Exception as e:
            logger.error(f"Unexpected authentication error: {str(e)}", exc_info=True)
            await self.close(code=WebSocketCloseCode.UNEXPECTED_AUTH_ERROR.value)
            return False

    async def _setup_user_group(self) -> bool:
        """Sets up user's WebSocket group with improved error handling"""
        try:
            self.user_group = f"notification_updates_{self.user.id}"
            await self.channel_layer.group_add(self.user_group, self.channel_name)
            return True
            
        except Exception as e:
            logger.error(f"Error setting up user group: {str(e)}", exc_info=True)
            await self.close(code=WebSocketCloseCode.GROUP_SETUP_ERROR.value)
            return False

    async def _heartbeat_monitor(self) -> None:
        """Monitors connection health with periodic heartbeats"""
        while self.is_connected:
            try:
                await self.send(text_data=json.dumps({'type': 'heartbeat'}, cls=CustomJSONEncoder))
                await asyncio.sleep(self.config.HEARTBEAT_INTERVAL)
            except Exception as e:
                logger.error(f"Heartbeat error: {str(e)}")
                break

    async def disconnect(self, close_code: int) -> None:
        """Handles disconnection with improved cleanup"""
        try:
            if hasattr(self, 'user_group'):
                await self.channel_layer.group_discard(
                    self.user_group, 
                    self.channel_name
                )
            
            self.is_connected = False
            
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
                try:
                    await self.heartbeat_task
                except asyncio.CancelledError:
                    pass
            
            # Cancel any pending tasks
            tasks = [
                task for task in asyncio.all_tasks() 
                if task.get_name().startswith(f"notification_updates_{self.user.id}")
            ]
            for task in tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}", exc_info=True)
        finally:
            if hasattr(self, 'close'):
                await self.close()

    async def send_initial_data(self) -> None:
        """Sends initial data with improved error handling"""
        try:
            if not self.is_connected:
                return
                
            data = {
                'user_group': self.user_group,
                'connected_at': timezone.now().isoformat(),
                'user_id': self.user.id
            }
            
            await self.send(text_data=json.dumps({
                'type': 'initial_data',
                'data': data
            }, cls=CustomJSONEncoder))
            
        except Exception as e:
            logger.error(f"Error sending initial data: {str(e)}", exc_info=True)
            if self.is_connected:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': "Failed to load initial data"
                }, cls=CustomJSONEncoder))

    async def receive(self, text_data: str) -> None:
        """Handles incoming messages with validation"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'heartbeat_response':
                return
            
            # Handle other message types here
            await self.send(text_data=json.dumps({
                'type': 'acknowledgment',
                'message': f'Received message of type: {message_type}'
            }, cls=CustomJSONEncoder))
            
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid message format'
            }, cls=CustomJSONEncoder))
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)

    # async def notification_message(self, event: Dict) -> None:
    #     """Handles incoming notifications and forwards them to the client"""
    #     try:
    #         await self.send(text_data=json.dumps({
    #             'type': 'notification',
    #             'data': event['data']
    #         }, cls=CustomJSONEncoder))
    #     except Exception as e:
    #         logger.error(f"Error sending notification: {str(e)}", exc_info=True)
    async def new_notification(self, event: Dict) -> None:
        """Handles incoming notifications and forwards them to the client"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'notification',
                'data': event['message']  # Correct key from 'message'
            }, cls=CustomJSONEncoder))
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}", exc_info=True)