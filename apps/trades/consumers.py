from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.core.cache import cache
from typing import Dict, List, Optional
import json
from decimal import Decimal
from datetime import timedelta
import logging
import asyncio
from urllib.parse import parse_qs
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# Create a database-specific sync_to_async decorator
db_sync_to_async = sync_to_async(thread_sensitive=True)

class DecimalEncoder(json.JSONEncoder):
    """
    Custom JSON encoder to handle Decimal objects.
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class TradeUpdateManager:
    """Utility class for managing trade caching and plan level access."""
    
    CACHE_TIMEOUT = 3600  # Cache duration in seconds (1 hour)
    RETRY_DELAY = 0.5     # Delay between retry attempts in seconds

    @staticmethod
    async def get_cached_trades(cache_key: str) -> Optional[Dict]:
        """Retrieve cached trade data asynchronously."""
        try:
            return await sync_to_async(cache.get)(cache_key)
        except Exception as e:
            logger.error(f"Failed to get cached trades: {str(e)}")
            return None

    @staticmethod
    async def set_cached_trades(cache_key: str, data: Dict):
        """Store trade data in the cache asynchronously."""
        try:
            await sync_to_async(cache.set)(cache_key, data, TradeUpdateManager.CACHE_TIMEOUT)
        except Exception as e:
            logger.error(f"Failed to set cached trades: {str(e)}")

    @staticmethod
    def  get_plan_levels(plan_type: str) -> List[str]:
        """Get accessible plan levels for a given plan type."""
        return {
            'BASIC': ['BASIC'],
            'PREMIUM': ['BASIC', 'PREMIUM'],
            'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
        }.get(plan_type, [])


class TradeUpdatesConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for delivering real-time trade updates to authenticated users.
    """
    
    RECONNECT_DELAY = 2   # Delay between reconnection attempts in seconds
    MAX_RETRIES = 3       # Maximum number of reconnection attempts

    ERROR_MESSAGES = {
        4001: "No authentication token provided. Please log in and try again.",
        4002: "Invalid or expired token. Please log in again.",
        4003: "Authentication failed. Please verify your credentials.",
        4004: "An unexpected error occurred during authentication.",
        4005: "No active subscription found. Please subscribe to continue.",
        4006: "Failed to set up trade updates. Please try again later.",
        4007: "Maximum connection retries exceeded. Please check your network and try again."
    }

    SUCCESS_MESSAGES = {
        "connected": "Successfully connected to trade updates.",
        "initial_data": "Initial trade data loaded successfully.",
        "trade_update": "Trade update received successfully."
    }

    def __init__(self, *args, **kwargs):
        """Initialize the consumer with default attributes."""
        super().__init__(*args, **kwargs)
        self.user = None
        self.subscription = None
        self.trade_manager = TradeUpdateManager()
        self.is_connected = False
        self.connection_retries = 0
        self.active_trade_count = 0
        self.stock_limit = None
        self.user_group = None
        self._initial_data_task = None

    async def connect(self):
        """
        Handle WebSocket connection establishment.
        """
        if self.connection_retries >= self.MAX_RETRIES:
            await self.send_error(4007)
            await self.close(code=4007)
            return

        try:
            if not await self._authenticate():
                return

            self.is_connected = True
            await self.accept()
            await self.send_success("connected")
            if await self._setup_user_group():
                self._initial_data_task = asyncio.create_task(self.send_initial_data())
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            self.connection_retries += 1
            await asyncio.sleep(self.RECONNECT_DELAY)
            await self.connect()

    async def send_error(self, code: int, extra_info: str = None):
        """Send an error message to the client."""
        message = self.ERROR_MESSAGES.get(code, "An unexpected error occurred.")
        if extra_info:
            message += f" Details: {extra_info}"
        await self.send(text_data=json.dumps({
            "type": "error",
            "code": code,
            "message": message
        }))

    async def send_success(self, event: str, extra_info: str = None):
        """Send a success message to the client."""
        message = self.SUCCESS_MESSAGES.get(event, "Operation completed successfully.")
        if extra_info:
            message += f" {extra_info}"
        await self.send(text_data=json.dumps({
            "type": "success",
            "event": event,
            "message": message
        }))

    async def _authenticate(self) -> bool:
        """Authenticate the user using a JWT token."""
        try:
            query_string = self.scope.get('query_string', b'').decode('utf-8')
            token = parse_qs(query_string).get('token', [None])[0]

            if not token:
                await self.send_error(4001)
                await self.close(code=4001)
                return False

            jwt_auth = JWTAuthentication()
            validated_token = await sync_to_async(jwt_auth.get_validated_token)(token)
            self.user = await sync_to_async(jwt_auth.get_user)(validated_token)

            if not self.user or not self.user.is_authenticated:
                await self.send_error(4003)
                await self.close(code=4003)
                return False

            return True
        except (InvalidToken, TokenError):
            await self.send_error(4002)
            await self.close(code=4002)
            return False
        except Exception as e:
            await self.send_error(4004, str(e))
            await self.close(code=4004)
            return False

    @db_sync_to_async
    def _get_active_subscription(self, user):
        """Fetch the user's active subscription synchronously."""
        from apps.subscriptions.models import Subscription
        now = timezone.now()
        return Subscription.objects.filter(
            user=user,
            is_active=True,
            start_date__lte=now,
            end_date__gte=now
        ).select_related('plan').first()

    async def _setup_user_group(self) -> bool:
        """Set up the user's channel group and subscription details."""
        try:
            self.subscription = await self._get_active_subscription(self.user)
            if not self.subscription:
                await self.send_error(4005)
                await self.close(code=4005)
                return False

            self.user_group = f"trade_updates_{self.user.id}"
            self.stock_limit = None if self.subscription.plan.name == 'SUPER_PREMIUM' else self.subscription.plan.stock_coverage
            await self.channel_layer.group_add(self.user_group, self.channel_name)
            return True
        except Exception as e:
            await self.send_error(4006, str(e))
            await self.close(code=4006)
            return False

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        try:
            if self.user_group:
                await self.channel_layer.group_discard(self.user_group, self.channel_name)
            self.is_connected = False
            if self._initial_data_task and not self._initial_data_task.done():
                self._initial_data_task.cancel()
        except Exception as e:
            logger.error(f"Disconnect error: {str(e)}")
        finally:
            await self.close()

    async def _get_filtered_trades(self) -> Dict:
        """
        Fetch and filter trade data based on user's subscription.

        Returns:
            Dict: Filtered stock and index trade data.

        Notes:
            - Reverted to sync-to-async for compatibility.
            - Added logging to debug empty results.
        """
        try:
            if not self.subscription or not self.subscription.plan:
                logger.warning("No subscription or plan found")
                return {'stock_data': [], 'index_data': []}

            cache_key = f"trades_data_{self.user.id}_{self.subscription.plan.name}"
            cached_data = await self.trade_manager.get_cached_trades(cache_key)
            if cached_data:
                logger.debug(f"Returning cached data for key: {cache_key}")
                self.active_trade_count = len(cached_data['stock_data'])
                return cached_data

            allowed_levels = TradeUpdateManager.get_plan_levels(self.subscription.plan.name)
            lookback_date = self.subscription.start_date - timedelta(days=30)

            from .models import Company
            from apps.indexAndCommodity.models import IndexAndCommodity
            from .serializers.tradeconsumer_serializers import CompanySerializer, IndexAndCommoditySeraializer

            # Fetch data synchronously but with better logging
            @sync_to_async
            def fetch_data():
                company_qs = Company.objects.filter(
                    trades__status="ACTIVE",
                    trades__created_at__date__gte=lookback_date,
                    trades__created_at__date__lte=self.subscription.end_date,
                    trades__plan_type__in=allowed_levels
                ).prefetch_related('trades').distinct()[:self.stock_limit or None]

                index_qs = IndexAndCommodity.objects.filter(
                    trades__status="ACTIVE",
                    trades__created_at__date__gte=lookback_date,
                    trades__created_at__date__lte=self.subscription.end_date,
                    trades__plan_type__in=allowed_levels
                ).prefetch_related('trades').distinct()

                company_count = company_qs.count()
                index_count = index_qs.count()
                logger.debug(f"Queried {company_count} companies and {index_count} indices")

                if company_count == 0 and index_count == 0:
                    logger.warning("No trades found matching filter criteria")

                company_items = [CompanySerializer(company).data for company in company_qs]
                index_items = [IndexAndCommoditySeraializer(index).data for index in index_qs]
                return company_items, index_items

            company_items, index_items = await fetch_data()
            self.active_trade_count = len(company_items)
            data = {'stock_data': company_items, 'index_data': index_items}

            if not company_items and not index_items:
                logger.warning(f"No data to cache for user {self.user.id}, plan {self.subscription.plan.name}")
            else:
                await self.trade_manager.set_cached_trades(cache_key, data)

            return data
        except Exception as e:
            logger.error(f"Error getting filtered trades: {str(e)}")
            return {'stock_data': [], 'index_data': []}

    async def send_initial_data(self):
        """Send initial trade data to the client after connection."""
        try:
            data = await self._get_filtered_trades()
            logger.debug(f"Sending initial data: stock={len(data['stock_data'])}, index={len(data['index_data'])}")
            await self.send(text_data=json.dumps({
                'type': 'initial_data',
                **data
            }, cls=DecimalEncoder))
            # await self.send(text_data=json.dumps(trades, cls=DecimalEncoder))
            await self.send_success("initial_data")
        except asyncio.CancelledError:
            logger.debug("Initial data task cancelled")
        except Exception as e:
            logger.error(f"Error sending initial data: {str(e)}")

    async def trade_update(self, event):
        """Handle trade update messages."""
        try:
            if not self.is_connected or not self.subscription:
                return

            data = event["data"]
            trade = await self.get_trade(data["trade_id"])

            if not trade or not await self.is_trade_accessible(trade):
                logger.warning(f"Trade {data['trade_id']} not accessible to user {self.user.id}")
                return

            # Create notification
            await self.create_notification(trade, data)

            # Format and send trade update
            trade_data = await self.format_trade_data(trade)
            
            # Add subscription info
            response_data = {
                "type": "trade_update",
                "data": {
                    **data,
                    "trade": trade_data,
                    "subscription": {
                        "plan": self.subscription.plan.name,
                        "expires_at": self.subscription.end_date.isoformat()
                    }
                }
            }

            logger.info(f"Sending trade update to user {self.user.id}: {response_data}")
            await self.send_json(response_data)

        except Exception as e:
            logger.error(f"Error handling trade update: {str(e)}")
            await self.send_json({
                "type": "error",
                "data": {
                    "message": "Error processing trade update",
                    "error": str(e)
                }
            })

    @db_sync_to_async
    def get_trade(self, trade_id):
        """Get trade by ID with optimized query."""
        try:
            return Trade.objects.select_related(
                'company',
                'analysis'
            ).prefetch_related(
                'history'
            ).get(id=trade_id)
        except Trade.DoesNotExist:
            logger.warning(f"Trade {trade_id} not found")
            return None

    @db_sync_to_async
    def is_trade_accessible(self, trade):
        """Check if user has access to the trade."""
        try:
            return trade.is_accessible_to_user(self.user)
        except Exception as e:
            logger.error(f"Error checking trade access: {str(e)}")
            return False

    @db_sync_to_async
    def create_notification(self, trade, data):
        """Create a notification for the trade update."""
        try:
            message = f"Trade update for {trade.company.trading_symbol}: {data.get('action', 'updated')}"
            priority = TradeNotification.Priority.HIGH if data.get("trade_status") == Trade.Status.ACTIVE else TradeNotification.Priority.NORMAL
            
            notification = TradeNotification.create_trade_notification(
                user=self.user,
                trade=trade,
                notification_type=TradeNotification.NotificationType.TRADE_UPDATE,
                message=message,
                priority=priority
            )
            logger.info(f"Created notification for trade {trade.id} for user {self.user.id}")
            return notification
        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            return None

    async def format_trade_data(self, trade):
        """Format trade data for WebSocket response."""
        return {
            "id": trade.id,
            "company": {
                "id": trade.company.id,
                "symbol": trade.company.trading_symbol,
                "name": trade.company.script_name
            },
            "status": trade.status,
            "action": trade.action,
            "plan_type": trade.plan_type,
            "created_at": trade.created_at.isoformat(),
            "updated_at": trade.updated_at.isoformat(),
            "analysis": {
                "sentiment": trade.analysis.status if hasattr(trade, 'analysis') else None,
                "bull_scenario": trade.analysis.bull_scenario if hasattr(trade, 'analysis') else None,
                "bear_scenario": trade.analysis.bear_scenario if hasattr(trade, 'analysis') else None
            } if hasattr(trade, 'analysis') else None
        }

    async def send_json(self, data):
        """Send JSON data to WebSocket."""
        await self.send(text_data=json.dumps(data, cls=DecimalEncoder))
