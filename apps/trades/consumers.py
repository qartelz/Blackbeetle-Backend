from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.core.cache import cache
from typing import Dict, List, Optional
import json
from decimal import Decimal
import logging
import asyncio
from urllib.parse import parse_qs
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.db import transaction
from apps.subscriptions.models import Subscription
from apps.trades.models import Trade

logger = logging.getLogger(__name__)

# Database-specific sync_to_async decorator
db_sync_to_async = sync_to_async(thread_sensitive=True)

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle Decimal objects."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

class TradeUpdateManager:
    """Utility class for managing trade caching and plan level access."""
    
    CACHE_TIMEOUT = 3600  # Cache duration in seconds (1 hour)
    
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
    def get_plan_levels(plan_type: str) -> List[str]:
        """Get accessible plan levels for a given plan type."""
        return {
            'BASIC': ['BASIC'],
            'PREMIUM': ['BASIC', 'PREMIUM'],
            'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM'],
            'FREE_TRIAL': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
        }.get(plan_type, [])

class TradeUpdatesConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for delivering real-time trade updates to authenticated users."""
    
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
        self.user_group = None
        self._initial_data_task = None
        # Trade limits based on plan type (now counting companies, not individual trades)
        self.company_limits = {
            'BASIC': {
                'new': 6,
                'previous': 6,
                'total': 12
            },
            'PREMIUM': {
                'new': 9,
                'previous': 6,
                'total': 15
            },
            'SUPER_PREMIUM': {
                'new': None,  # No limit
                'previous': None,  # No limit
                'total': None  # No limit
            },
            'FREE_TRIAL': {
                'new': None,  # No limit
                'previous': None,  # No limit
                'total': None  # No limit
            }
        }

    async def connect(self):
        """Handle WebSocket connection establishment."""
        if self.connection_retries >= self.MAX_RETRIES:
            await self.close(code=4007)
            return

        try:
            # Accept the connection first
            await self.accept()
            
            # Then authenticate
            if not await self._authenticate():
                await self.close(code=4003)
                return

            self.is_connected = True
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
            # Try to get token from URL parameters first
            token = self.scope['url_route']['kwargs'].get('token')
            
            # If not in URL, try query parameters
            if not token:
                query_string = self.scope.get('query_string', b'').decode('utf-8')
                parsed_qs = parse_qs(query_string)
                token = parsed_qs.get('token', [None])[0] or parsed_qs.get('access_token', [None])[0]

            if not token:
                await self.send_error(4001)
                return False

            # Authenticate using the token
            jwt_auth = JWTAuthentication()
            validated_token = await sync_to_async(jwt_auth.get_validated_token)(token)
            self.user = await sync_to_async(jwt_auth.get_user)(validated_token)

            if not self.user or not self.user.is_authenticated:
                await self.send_error(4003)
                return False

            return True
        except (InvalidToken, TokenError):
            await self.send_error(4002)
            return False
        except Exception as e:
            await self.send_error(4004, str(e))
            return False

    @db_sync_to_async
    def _get_active_subscription(self, user):
        """Fetch the user's active subscription synchronously."""
        try:
            from apps.subscriptions.models import Subscription
            
            with transaction.atomic():
                now = timezone.now()
                logger.info(f"Checking subscription for user {user.id} at {now}")
                
                # Get all subscriptions for debugging
                all_subs = Subscription.objects.filter(user=user).values(
                    'id', 'is_active', 'start_date', 'end_date', 'plan__name'
                )
                logger.info(f"All subscriptions for user: {list(all_subs)}")
                
                # Get active subscription
                subscription = Subscription.objects.filter(
                    user=user,
                    is_active=True
                ).select_related('plan').first()
                
                if subscription:
                    logger.info(f"Found subscription: {subscription.id}, plan: {subscription.plan.name}")
                    logger.info(f"Subscription dates - Start: {subscription.start_date}, End: {subscription.end_date}")
                    return subscription
                else:
                    logger.warning(f"No subscription found for user {user.id}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting active subscription: {str(e)}")
            return None

    async def _setup_user_group(self) -> bool:
        """Set up the user's channel group and subscription details."""
        try:
            self.subscription = await self._get_active_subscription(self.user)
            if not self.subscription:
                logger.error(f"No subscription found for user {self.user.id}")
                await self.send_error(4005)
                return False

            # Set up user group
            self.user_group = f"trade_updates_{self.user.id}"
            
            # Add to channel group
            await self.channel_layer.group_add(self.user_group, self.channel_name)
            logger.info(f"Added user {self.user.id} to group {self.user_group}")
            
            # Send subscription info
            await self.send(text_data=json.dumps({
                'type': 'subscription_info',
                'data': {
                    'plan': self.subscription.plan.name,
                    'start_date': self.subscription.start_date.isoformat(),
                    'end_date': self.subscription.end_date.isoformat(),
                    'limits': self.company_limits.get(self.subscription.plan.name, {'new': None, 'previous': None, 'total': None})
                }
            }))
            
            return True

        except Exception as e:
            logger.error(f"Error setting up user group: {str(e)}")
            await self.send_error(4006, str(e))
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

    @db_sync_to_async
    def _get_filtered_company_data(self):
        """Get filtered and grouped company data based on subscription plan."""
        from .models import Trade, Company
        from django.db.models import Prefetch
        
        try:
            with transaction.atomic():
                logger.info(f"Getting filtered company data for user {self.user.id}")
                
                # Get plan levels accessible to this user
                plan_levels = self.trade_manager.get_plan_levels(self.subscription.plan.name)
                
                # Get company limits based on plan
                limits = self.company_limits.get(self.subscription.plan.name, {'new': None, 'previous': None})
                
                # Start by getting all companies with active trades
                all_companies = Company.objects.prefetch_related(
                    Prefetch(
                        'trades',
                        queryset=Trade.objects.filter(
                            status='ACTIVE',
                            plan_type__in=plan_levels
                        ).select_related('analysis').prefetch_related('history'),
                        to_attr='filtered_trades'
                    )
                ).filter(
                    trades__status='ACTIVE',
                    trades__plan_type__in=plan_levels
                ).distinct()
                
                # Separate companies into new and previous based on subscription date
                previous_companies = []  # Companies with trades before subscription
                new_companies = []       # Companies with trades after subscription
                
                # Process each company
                company_list = list(all_companies)
                for company in company_list:
                    # Group trades by type (intraday/positional) and keep only the most recent of each
                    intraday_trade = None
                    positional_trade = None
                    
                    active_trades = company.filtered_trades
                    
                    # Check if there are any trades after subscription date
                    post_subscription_trades = [
                        t for t in active_trades 
                        if t.created_at >= self.subscription.start_date
                    ]
                    
                    # Check if there are any trades before subscription date
                    pre_subscription_trades = [
                        t for t in active_trades 
                        if t.created_at < self.subscription.start_date
                    ]
                    
                    # If company has trades after subscription, add to new companies
                    if post_subscription_trades:
                        # Find most recent intraday and positional trades
                        for trade in sorted(post_subscription_trades, key=lambda t: t.created_at, reverse=True):
                            if trade.trade_type == 'INTRADAY' and intraday_trade is None:
                                intraday_trade = trade
                            elif trade.trade_type == 'POSITIONAL' and positional_trade is None:
                                positional_trade = trade
                            
                            # Break if we've found both types
                            if intraday_trade and positional_trade:
                                break
                        
                        # Build company data structure
                        company_data = {
                            'id': company.id,
                            'tradingSymbol': company.trading_symbol,
                            'exchange': company.exchange,
                            'instrumentName': self._get_instrument_name(company.instrument_type),
                            'intraday_trade': self._format_trade(intraday_trade) if intraday_trade else None,
                            'positional_trade': self._format_trade(positional_trade) if positional_trade else None,
                            'created_at': max([t.created_at for t in post_subscription_trades]).isoformat() if post_subscription_trades else None
                        }
                        new_companies.append(company_data)
                    
                    # If company has trades before subscription, add to previous companies
                    elif pre_subscription_trades:
                        # Find most recent intraday and positional trades
                        for trade in sorted(pre_subscription_trades, key=lambda t: t.created_at, reverse=True):
                            if trade.trade_type == 'INTRADAY' and intraday_trade is None:
                                intraday_trade = trade
                            elif trade.trade_type == 'POSITIONAL' and positional_trade is None:
                                positional_trade = trade
                            
                            # Break if we've found both types
                            if intraday_trade and positional_trade:
                                break
                        
                        # Build company data structure
                        company_data = {
                            'id': company.id,
                            'tradingSymbol': company.trading_symbol,
                            'exchange': company.exchange,
                            'instrumentName': self._get_instrument_name(company.instrument_type),
                            'intraday_trade': self._format_trade(intraday_trade) if intraday_trade else None,
                            'positional_trade': self._format_trade(positional_trade) if positional_trade else None,
                            'created_at': max([t.created_at for t in pre_subscription_trades]).isoformat() if pre_subscription_trades else None
                        }
                        previous_companies.append(company_data)
                
                # Sort companies by created_at date (most recent first)
                new_companies.sort(key=lambda x: x['created_at'] if x['created_at'] else '', reverse=True)
                previous_companies.sort(key=lambda x: x['created_at'] if x['created_at'] else '', reverse=True)
                
                # Apply limits if necessary
                if limits['new'] is not None:
                    new_companies = new_companies[:limits['new']]
                
                if limits['previous'] is not None:
                    previous_companies = previous_companies[:limits['previous']]
                
                logger.info(f"Found {len(new_companies)} new companies and {len(previous_companies)} previous companies")
                
                # Return structured data
                return {
                    'stock_data': new_companies + previous_companies,
                    'index_data': []  # Include empty index_data as in your example
                }
                
        except Exception as e:
            logger.error(f"Error getting filtered company data: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {'stock_data': [], 'index_data': []}
    
    def _get_instrument_name(self, instrument_type):
        """Map instrument type to display name."""
        instrument_mapping = {
            'EQUITY': 'EQUITY',
            'FNO_FUT': 'F&O',
            'FNO_CE': 'F&O',
            'FNO_PE': 'F&O',
        }
        return instrument_mapping.get(instrument_type, instrument_type)
    
    def _format_trade(self, trade):
        """Format trade data for WebSocket response."""
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

    async def send_initial_data(self):
        """Send initial trade data to the client."""
        try:
            data = await self._get_filtered_company_data()
            logger.info(f"Sending initial data with {len(data['stock_data'])} companies")
            
            await self.send(text_data=json.dumps({
                'type': 'initial_data',
                'stock_data': data['stock_data'],
                'index_data': data['index_data']
            }, cls=DecimalEncoder))
            
            await self.send_success("initial_data")
            
        except asyncio.CancelledError:
            logger.debug("Initial data task cancelled")
        except Exception as e:
            logger.error(f"Error sending initial data: {str(e)}")
            await self.send_error(4006, str(e))

    async def trade_update(self, event):
        """Handle trade update messages."""
        logger.info(f"WS consumer received trade_update event: {event}")
        try:
            if not self.is_connected or not self.subscription:
                logger.warning("Consumer not connected or no subscription")
                return

            data = event["data"]
            logger.info(f"Processing trade update for trade_id: {data['trade_id']}")
            
            # Get updated company data that contains this trade
            updated_company = await self._get_company_with_trade(data["trade_id"])
            if not updated_company:
                logger.warning(f"Company with trade {data['trade_id']} not found")
                return

            # Check if the company is accessible based on subscription limits
            if not await self._is_company_accessible(updated_company['id']):
                logger.warning(f"Company {updated_company['id']} not accessible to user {self.user.id}")
                return
            
            # Prepare response data
            response_data = {
                "type": "trade_update",
                "data": {
                    "updated_company": updated_company,
                    "subscription": {
                        "plan": self.subscription.plan.name,
                        "expires_at": self.subscription.end_date.isoformat(),
                        "limits": self.company_limits.get(self.subscription.plan.name, 
                                                         {'new': None, 'previous': None, 'total': None})
                    }
                }
            }

            logger.info("Sending trade update to WebSocket")
            await self.send(text_data=json.dumps(response_data, cls=DecimalEncoder))
            logger.info("Trade update sent successfully")

        except Exception as e:
            logger.error(f"Error handling trade update: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            await self.send(text_data=json.dumps({
                "type": "error",
                "data": {
                    "message": "Error processing trade update",
                    "error": str(e)
                }
            }, cls=DecimalEncoder))

    @db_sync_to_async
    def _get_company_with_trade(self, trade_id):
        """Get company data that contains the specified trade."""
        from .models import Trade, Company
        
        try:
            with transaction.atomic():
                # Get the trade and its associated company
                trade = Trade.objects.select_related(
                    'company', 'analysis'
                ).prefetch_related(
                    'history'
                ).get(id=trade_id)
                
                company = trade.company
                
                # Get all active trades for this company
                active_trades = Trade.objects.filter(
                    company=company,
                    status='ACTIVE',
                    plan_type__in=self.trade_manager.get_plan_levels(self.subscription.plan.name)
                ).select_related('analysis').prefetch_related('history')
                
                # Group by trade type
                intraday_trade = None
                positional_trade = None
                
                for t in active_trades:
                    if t.trade_type == 'INTRADAY' and (intraday_trade is None or t.created_at > intraday_trade.created_at):
                        intraday_trade = t
                    elif t.trade_type == 'POSITIONAL' and (positional_trade is None or t.created_at > positional_trade.created_at):
                        positional_trade = t
                
                # Format company data
                company_data = {
                    'id': company.id,
                    'tradingSymbol': company.trading_symbol,
                    'exchange': company.exchange,
                    'instrumentName': self._get_instrument_name(company.instrument_type),
                    'intraday_trade': self._format_trade(intraday_trade) if intraday_trade else None,
                    'positional_trade': self._format_trade(positional_trade) if positional_trade else None,
                    'created_at': max([t.created_at for t in active_trades]).isoformat() if active_trades else None
                }
                
                return company_data
                
        except Trade.DoesNotExist:
            logger.warning(f"Trade {trade_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error getting company with trade {trade_id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    @db_sync_to_async
    def _is_company_accessible(self, company_id):
        """Check if user has access to the company based on subscription limits."""
        from .models import Company, Trade
        
        try:
            with transaction.atomic():
                if not self.subscription:
                    return False
                    
                # For SUPER_PREMIUM and FREE_TRIAL, all companies are accessible
                if self.subscription.plan.name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
                    return True
                
                # Get accessible plan levels
                plan_levels = self.trade_manager.get_plan_levels(self.subscription.plan.name)
                
                # Find this company's position in the list of all companies
                company = Company.objects.get(id=company_id)
                
                # Check if company has any trades created after subscription
                has_post_subscription_trades = Trade.objects.filter(
                    company=company,
                    created_at__gte=self.subscription.start_date,
                    status='ACTIVE',
                    plan_type__in=plan_levels
                ).exists()
                
                if has_post_subscription_trades:
                    # Get all companies with post-subscription trades
                    companies_with_post_trades = Company.objects.filter(
                        trades__created_at__gte=self.subscription.start_date,
                        trades__status='ACTIVE',
                        trades__plan_type__in=plan_levels
                    ).distinct().order_by('trades__created_at')
                    
                    # Check if this company is within the limit
                    company_position = list(companies_with_post_trades).index(company) if company in companies_with_post_trades else -1
                    
                    if company_position == -1:
                        return False
                        
                    # Get limit for new companies
                    new_limit = self.company_limits.get(self.subscription.plan.name, {}).get('new')
                    if new_limit is None:  # No limit
                        return True
                        
                    return company_position < new_limit
                else:
                    # Check for pre-subscription trades
                    has_pre_subscription_trades = Trade.objects.filter(
                        company=company,
                        created_at__lt=self.subscription.start_date,
                        status='ACTIVE',
                        plan_type__in=plan_levels
                    ).exists()
                    
                    if not has_pre_subscription_trades:
                        return False
                        
                    # Get all companies with pre-subscription trades
                    companies_with_pre_trades = Company.objects.filter(
                        trades__created_at__lt=self.subscription.start_date,
                        trades__status='ACTIVE',
                        trades__plan_type__in=plan_levels
                    ).distinct().order_by('trades__created_at')
                    
                    # Check if this company is within the limit
                    company_position = list(companies_with_pre_trades).index(company) if company in companies_with_pre_trades else -1
                    
                    if company_position == -1:
                        return False
                        
                    # Get limit for previous companies
                    previous_limit = self.company_limits.get(self.subscription.plan.name, {}).get('previous')
                    if previous_limit is None:  # No limit
                        return True
                        
                    return company_position < previous_limit
                    
        except Exception as e:
            logger.error(f"Error checking company access: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False




# from channels.generic.websocket import AsyncWebsocketConsumer
# from asgiref.sync import sync_to_async
# from django.core.cache import cache
# from typing import Dict, List, Optional
# import json
# from decimal import Decimal
# from datetime import timedelta
# import logging
# import asyncio
# from urllib.parse import parse_qs
# from django.utils import timezone
# from rest_framework_simplejwt.authentication import JWTAuthentication
# from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from django.db import transaction
# from apps.subscriptions.models import Subscription
# from .models import Trade, TradeNotification, Company
# import traceback

# logger = logging.getLogger(__name__)

# # Create a database-specific sync_to_async decorator
# db_sync_to_async = sync_to_async(thread_sensitive=True)

# # Global Trade model reference
# TRADE_MODEL = Trade

# class DecimalEncoder(json.JSONEncoder):
#     """
#     Custom JSON encoder to handle Decimal objects.
#     """
#     def default(self, obj):
#         if isinstance(obj, Decimal):
#             return str(obj)
#         return super().default(obj)


# class TradeUpdateManager:
#     """Utility class for managing trade caching and plan level access."""
    
#     CACHE_TIMEOUT = 3600  # Cache duration in seconds (1 hour)
#     RETRY_DELAY = 0.5     # Delay between retry attempts in seconds

#     @staticmethod
#     async def get_cached_trades(cache_key: str) -> Optional[Dict]:
#         """Retrieve cached trade data asynchronously."""
#         try:
#             return await sync_to_async(cache.get)(cache_key)
#         except Exception as e:
#             logger.error(f"Failed to get cached trades: {str(e)}")
#             return None

#     @staticmethod
#     async def set_cached_trades(cache_key: str, data: Dict):
#         """Store trade data in the cache asynchronously."""
#         try:
#             await sync_to_async(cache.set)(cache_key, data, TradeUpdateManager.CACHE_TIMEOUT)
#         except Exception as e:
#             logger.error(f"Failed to set cached trades: {str(e)}")

#     @staticmethod
#     def  get_plan_levels(plan_type: str) -> List[str]:
#         """Get accessible plan levels for a given plan type."""
#         return {
#             'BASIC': ['BASIC'],
#             'PREMIUM': ['BASIC', 'PREMIUM'],
#             'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
#         }.get(plan_type, [])


# class TradeUpdatesConsumer(AsyncWebsocketConsumer):
#     """
#     WebSocket consumer for delivering real-time trade updates to authenticated users.
#     """
    
#     RECONNECT_DELAY = 2   # Delay between reconnection attempts in seconds
#     MAX_RETRIES = 3       # Maximum number of reconnection attempts

#     ERROR_MESSAGES = {
#         4001: "No authentication token provided. Please log in and try again.",
#         4002: "Invalid or expired token. Please log in again.",
#         4003: "Authentication failed. Please verify your credentials.",
#         4004: "An unexpected error occurred during authentication.",
#         4005: "No active subscription found. Please subscribe to continue.",
#         4006: "Failed to set up trade updates. Please try again later.",
#         4007: "Maximum connection retries exceeded. Please check your network and try again."
#     }

#     SUCCESS_MESSAGES = {
#         "connected": "Successfully connected to trade updates.",
#         "initial_data": "Initial trade data loaded successfully.",
#         "trade_update": "Trade update received successfully."
#     }

#     def __init__(self, *args, **kwargs):
#         """Initialize the consumer with default attributes."""
#         super().__init__(*args, **kwargs)
#         self.user = None
#         self.subscription = None
#         self.trade_manager = TradeUpdateManager()
#         self.is_connected = False
#         self.connection_retries = 0
#         self.active_trade_count = 0
#         self.stock_limit = None
#         self.user_group = None
#         self._initial_data_task = None
#         # Add trade limits for each plan type
#         self.trade_limits = {
#             'BASIC': {
#                 'new': 6,
#                 'previous': 6,
#                 'total': 12
#             },
#             'PREMIUM': {
#                 'new': 6,
#                 'previous': 6,
#                 'total': 12
#             },
#             'SUPER_PREMIUM': {
#                 'new': None,  # No limit
#                 'previous': None,  # No limit
#                 'total': None  # No limit
#             },
#             'FREE_TRIAL': {
#                 'new': None,  # No limit
#                 'previous': None,  # No limit
#                 'total': None  # No limit
#             }
#         }

#     async def connect(self):
#         """
#         Handle WebSocket connection establishment.
#         """
#         if self.connection_retries >= self.MAX_RETRIES:
#             await self.close(code=4007)
#             return

#         try:
#             # Accept the connection first
#             await self.accept()
            
#             # Then authenticate
#             if not await self._authenticate():
#                 await self.close(code=4003)
#                 return

#             self.is_connected = True
#             await self.send_success("connected")
            
#             if await self._setup_user_group():
#                 self._initial_data_task = asyncio.create_task(self.send_initial_data())

#         except Exception as e:
#             logger.error(f"Connection error: {str(e)}")
#             self.connection_retries += 1
#             await asyncio.sleep(self.RECONNECT_DELAY)
#             await self.connect()

#     async def send_error(self, code: int, extra_info: str = None):
#         """Send an error message to the client."""
#         message = self.ERROR_MESSAGES.get(code, "An unexpected error occurred.")
#         if extra_info:
#             message += f" Details: {extra_info}"
#         await self.send(text_data=json.dumps({
#             "type": "error",
#             "code": code,
#             "message": message
#         }))

#     async def send_success(self, event: str, extra_info: str = None):
#         """Send a success message to the client."""
#         message = self.SUCCESS_MESSAGES.get(event, "Operation completed successfully.")
#         if extra_info:
#             message += f" {extra_info}"
#         await self.send(text_data=json.dumps({
#             "type": "success",
#             "event": event,
#             "message": message
#         }))

#     async def _authenticate(self) -> bool:
#         """Authenticate the user using a JWT token."""
#         try:
#             query_string = self.scope.get('query_string', b'').decode('utf-8')
#             token = parse_qs(query_string).get('token', [None])[0]

#             if not token:
#                 await self.send_error(4001)
#                 return False

#             jwt_auth = JWTAuthentication()
#             validated_token = await sync_to_async(jwt_auth.get_validated_token)(token)
#             self.user = await sync_to_async(jwt_auth.get_user)(validated_token)

#             if not self.user or not self.user.is_authenticated:
#                 await self.send_error(4003)
#                 return False

#             return True
#         except (InvalidToken, TokenError):
#             await self.send_error(4002)
#             return False
#         except Exception as e:
#             await self.send_error(4004, str(e))
#             return False

#     @db_sync_to_async
#     def _get_active_subscription(self, user):
#         """Fetch the user's active subscription synchronously."""
#         try:
#             with transaction.atomic():
#                 now = timezone.now()
#                 logger.info(f"Checking subscription for user {user.id} at {now}")
                
#                 # Get all subscriptions for debugging
#                 all_subs = Subscription.objects.filter(user=user).values(
#                     'id', 'is_active', 'start_date', 'end_date', 'plan__name'
#                 )
#                 logger.info(f"All subscriptions for user: {list(all_subs)}")
                
#                 # Get active subscription
#                 subscription = Subscription.objects.filter(
#                     user=user,
#                     is_active=True
#                 ).select_related('plan').first()
                
#                 if subscription:
#                     logger.info(f"Found subscription: {subscription.id}, plan: {subscription.plan.name}")
#                     logger.info(f"Subscription dates - Start: {subscription.start_date}, End: {subscription.end_date}")
#                     return subscription
#                 else:
#                     logger.warning(f"No subscription found for user {user.id}")
#                     return None
                    
#         except Exception as e:
#             logger.error(f"Error getting active subscription: {str(e)}")
#             return None

#     async def _setup_user_group(self) -> bool:
#         """Set up the user's channel group and subscription details."""
#         try:
#             self.subscription = await self._get_active_subscription(self.user)
#             if not self.subscription:
#                 logger.error(f"No subscription found for user {self.user.id}")
#                 await self.send_error(4005)
#                 return False

#             # Set up user group and limits
#             self.user_group = f"trade_updates_{self.user.id}"
#             self.stock_limit = None if self.subscription.plan.name == 'SUPER_PREMIUM' else self.subscription.plan.stock_coverage
            
#             # Add to channel group
#             await self.channel_layer.group_add(self.user_group, self.channel_name)
#             logger.info(f"Added user {self.user.id} to group {self.user_group}")
            
#             # Send subscription info
#             await self.send(text_data=json.dumps({
#                 'type': 'subscription_info',
#                 'data': {
#                     'plan': self.subscription.plan.name,
#                     'start_date': self.subscription.start_date.isoformat(),
#                     'end_date': self.subscription.end_date.isoformat(),
#                     'stock_limit': self.stock_limit
#                 }
#             }))
            
#             return True

#         except Exception as e:
#             logger.error(f"Error setting up user group: {str(e)}")
#             await self.send_error(4006, str(e))
#             return False

#     async def disconnect(self, close_code):
#         """Handle WebSocket disconnection."""
#         try:
#             if self.user_group:
#                 await self.channel_layer.group_discard(self.user_group, self.channel_name)
#             self.is_connected = False
#             if self._initial_data_task and not self._initial_data_task.done():
#                 self._initial_data_task.cancel()
#         except Exception as e:
#             logger.error(f"Disconnect error: {str(e)}")
#         finally:
#             await self.close()

#     def format_trade(self, trade):
#         """Format trade data for WebSocket response."""
#         try:
#             formatted_trade = {
#                 'id': trade.id,
#                 'company': {
#                     'id': trade.company.id,
#                     'symbol': trade.company.trading_symbol,
#                     'name': trade.company.script_name
#                 },
#                 'status': trade.status,
#                 'trade_type': trade.trade_type,
#                 'plan_type': trade.plan_type,
#                 'warzone': str(trade.warzone),
#                 'image': trade.image.url if trade.image else None,
#                 'warzone_history': trade.warzone_history or [],
#                 'created_at': trade.created_at.isoformat(),
#                 'updated_at': trade.updated_at.isoformat(),
#                 'completed_at': trade.completed_at.isoformat() if trade.completed_at else None,
#                 'analysis': None,
#                 'trade_history': []
#             }

#             if hasattr(trade, 'analysis'):
#                 formatted_trade['analysis'] = {
#                     'bull_scenario': trade.analysis.bull_scenario,
#                     'bear_scenario': trade.analysis.bear_scenario,
#                     'status': trade.analysis.status,
#                     'completed_at': trade.analysis.completed_at.isoformat() if trade.analysis.completed_at else None,
#                     'created_at': trade.analysis.created_at.isoformat(),
#                     'updated_at': trade.analysis.updated_at.isoformat()
#                 }

#             if hasattr(trade, 'history'):
#                 formatted_trade['trade_history'] = [
#                     {
#                         'buy': str(history.buy),
#                         'target': str(history.target),
#                         'sl': str(history.sl),
#                         'timestamp': history.timestamp.isoformat()
#                     } for history in trade.history.all()
#                 ]

#             return formatted_trade
#         except Exception as e:
#             logger.error(f"Error formatting trade {trade.id}: {str(e)}")
#             return None

#     @db_sync_to_async
#     def _get_filtered_trades(self):
#         """Get filtered trades based on subscription plan."""
#         try:
#             from .models import Trade, Company
#             from apps.indexAndCommodity.models import IndexAndCommodity

#             now = timezone.now()
#             logger.info(f"User {self.user.id} subscription started at: {self.subscription.start_date}")
#             logger.info(f"Current time: {now}")

#             # Get the appropriate trade limit based on plan
#             trade_limit = None
#             if self.subscription.plan.name == 'BASIC':
#                 trade_limit = 6
#             elif self.subscription.plan.name == 'PREMIUM':
#                 trade_limit = 9
#             # SUPER_PREMIUM and FREE_TRIAL have no limit (trade_limit remains None)

#             # Get new trades (trades created after subscription)
#             new_trades = Trade.objects.filter(
#                 created_at__gte=self.subscription.start_date,
#                 status__in=['ACTIVE', 'COMPLETED'],
#                 plan_type__in=self.trade_manager.get_plan_levels(self.subscription.plan.name)
#             ).select_related(
#                 'company',
#                 'analysis'
#             ).prefetch_related(
#                 'history'
#             ).order_by('-created_at')

#             # Get previous trades (active trades that existed before subscription)
#             previous_trades = Trade.objects.filter(
#                 created_at__lt=self.subscription.start_date,
#                 status__in=['ACTIVE', 'COMPLETED'],
#                 plan_type__in=self.trade_manager.get_plan_levels(self.subscription.plan.name)
#             ).select_related(
#                 'company',
#                 'analysis'
#             ).prefetch_related(
#                 'history'
#             ).order_by('-created_at')

#             # Apply limits based on plan type
#             if trade_limit is not None:
#                 # For BASIC and PREMIUM, get the first N trades
#                 initial_trades = Trade.objects.filter(
#                     created_at__gte=self.subscription.start_date,
#                     plan_type__in=self.trade_manager.get_plan_levels(self.subscription.plan.name)
#                 ).order_by('created_at')[:trade_limit]
                
#                 # Filter new_trades to only include the initial trades
#                 new_trades = new_trades.filter(id__in=[t.id for t in initial_trades])
                
#                 # Limit previous trades to the same number
#                 previous_trades = previous_trades[:trade_limit]

#             logger.info(f"User {self.user.id}: {len(previous_trades)} previous trades, {len(new_trades)} new trades")
#             logger.info(f"Previous trades: {[t.id for t in previous_trades]}")
#             logger.info(f"New trades: {[t.id for t in new_trades]}")

#             # Format all trades
#             formatted_trades = {
#                 'previous_trades': [self.format_trade(t) for t in previous_trades],
#                 'new_trades': [self.format_trade(t) for t in new_trades]
#             }

#             return formatted_trades

#         except Exception as e:
#             logger.error(f"Error getting filtered trades: {str(e)}")
#             logger.error(f"Error traceback: {traceback.format_exc()}")
#             return {'previous_trades': [], 'new_trades': []}

#     async def send_initial_data(self):
#         """Send initial trade data to the client."""
#         try:
#             data = await self._get_filtered_trades()
#             logger.info(f"Sending initial data: previous={len(data['previous_trades'])}, new={len(data['new_trades'])}")
            
#             await self.send(text_data=json.dumps({
#                 'type': 'initial_data',
#                 'data': data
#             }, cls=DecimalEncoder))
            
#             await self.send_success("initial_data")
            
#         except asyncio.CancelledError:
#             logger.debug("Initial data task cancelled")
#         except Exception as e:
#             logger.error(f"Error sending initial data: {str(e)}")
#             await self.send_error(4006, str(e))

#     @db_sync_to_async
#     def _get_active_trade_count(self):
#         """Get count of active trades for the user."""
#         try:
#             with transaction.atomic():
#                 # Get new active trades (created after subscription)
#                 new_active = TRADE_MODEL.objects.filter(
#                     created_at__gte=self.subscription.start_date,
#                     status='ACTIVE'
#                 ).count()

#                 # Get previous active trades (created before subscription)
#                 previous_active = TRADE_MODEL.objects.filter(
#                     created_at__lt=self.subscription.start_date,
#                     status='ACTIVE'
#                 ).count()

#                 total_active = new_active + previous_active

#                 logger.info(f"Found {new_active} new active trades and {previous_active} previous active trades")
                
#                 return {
#                     'new_active': new_active,
#                     'previous_active': previous_active,
#                     'total_active': total_active
#                 }

#         except Exception as e:
#             logger.error(f"Error getting active trade count: {str(e)}")
#             logger.error(f"Error traceback: {traceback.format_exc()}")
#             return {
#                 'new_active': 0,
#                 'previous_active': 0,
#                 'total_active': 0
#             }

#     async def trade_update(self, event):
#         """Handle trade update messages."""
#         logger.info(f"WS consumer received trade_update event: {event}")
#         try:
#             if not self.is_connected or not self.subscription:
#                 logger.warning("Consumer not connected or no subscription")
#                 return

#             data = event["data"]
#             logger.info(f"Processing trade update for trade_id: {data['trade_id']}")
            
#             trade = await self.get_trade(data["trade_id"])
#             if not trade:
#                 logger.warning(f"Trade {data['trade_id']} not found")
#                 return

#             # For BASIC and PREMIUM plans, only allow updates to the initial trades
#             if self.subscription.plan.name in ['BASIC', 'PREMIUM']:
#                 trade_limit = 6 if self.subscription.plan.name == 'BASIC' else 9
#                 initial_trades = await self._get_initial_trades(trade_limit)
#                 if trade.id not in initial_trades:
#                     logger.warning(f"Trade {trade.id} not in initial {trade_limit} trades for {self.subscription.plan.name} plan")
#                     return

#             # Check if trade is accessible based on plan type and subscription date
#             if not await self.is_trade_accessible(trade):
#                 logger.warning(f"Trade {data['trade_id']} not accessible to user {self.user.id}")
#                 return

#             # Format trade data using the class method
#             trade_data = self.format_trade(trade)
#             logger.info(f"Formatted trade data: {trade_data}")
            
#             # Get updated active counts
#             active_counts = await self._get_active_trade_count()
#             logger.info(f"Active counts: {active_counts}")
            
#             # Get trade limits for the user's plan
#             plan_limits = self.trade_limits.get(self.subscription.plan.name, {
#                 'new': 0,
#                 'previous': 0,
#                 'total': 0
#             })
#             logger.info(f"Trade limits for plan {self.subscription.plan.name}: {plan_limits}")
            
#             # Prepare response data
#             response_data = {
#                 "type": "trade_update",
#                 "data": {
#                     "new_trades": [trade_data],  # Add to new_trades array to match format
#                     "subscription": {
#                         "plan": self.subscription.plan.name,
#                         "expires_at": self.subscription.end_date.isoformat(),
#                         "active_trades": active_counts,
#                         "trade_limits": plan_limits
#                     }
#                 }
#             }

#             logger.info(f"Sending trade update to WebSocket: {response_data}")
#             await self.send(text_data=json.dumps(response_data, cls=DecimalEncoder))
#             logger.info("Trade update sent successfully")

#         except Exception as e:
#             logger.error(f"Error handling trade update: {str(e)}")
#             logger.error(f"Error traceback: {traceback.format_exc()}")
#             await self.send(text_data=json.dumps({
#                 "type": "error",
#                 "data": {
#                     "message": "Error processing trade update",
#                     "error": str(e)
#                 }
#             }, cls=DecimalEncoder))

#     @db_sync_to_async
#     def get_trade(self, trade_id):
#         """Get trade by ID with optimized query."""
#         try:
#             with transaction.atomic():
#                 return TRADE_MODEL.objects.select_related(
#                     'company',
#                     'analysis'
#                 ).prefetch_related(
#                     'history'
#                 ).get(id=trade_id)
#         except TRADE_MODEL.DoesNotExist:
#             logger.warning(f"Trade {trade_id} not found")
#             return None
#         except Exception as e:
#             logger.error(f"Error getting trade {trade_id}: {str(e)}")
#             logger.error(f"Error traceback: {traceback.format_exc()}")
#             return None

#     @db_sync_to_async
#     def is_trade_accessible(self, trade):
#         """Check if user has access to the trade."""
#         try:
#             with transaction.atomic():
#                 # Use the subscription from the consumer instead of getting it from user
#                 if not self.subscription:
#                     logger.warning(f"No subscription found for user {self.user.id}")
#                     return False

#                 # Check if trade is within subscription period
#                 if trade.created_at < self.subscription.start_date:
#                     logger.info(f"Trade {trade.id} created before subscription start date")
#                     return False

#                 # Check plan type access
#                 if trade.plan_type not in self.trade_manager.get_plan_levels(self.subscription.plan.name):
#                     logger.info(f"Trade {trade.id} plan type {trade.plan_type} not accessible for user plan {self.subscription.plan.name}")
#                     return False

#                 return True

#         except Exception as e:
#             logger.error(f"Error checking trade access: {str(e)}")
#             logger.error(f"Error traceback: {traceback.format_exc()}")
#             return False

#     @db_sync_to_async
#     def create_notification(self, trade, data):
#         """Create a notification for the trade update."""
#         try:
#             with transaction.atomic():
#                 message = f"Trade update for {trade.company.trading_symbol}: {data.get('action', 'updated')}"
#                 priority = TradeNotification.Priority.HIGH if data.get("trade_status") == Trade.Status.ACTIVE else TradeNotification.Priority.NORMAL
                
#                 notification = TradeNotification.create_trade_notification(
#                     user=self.user,
#                     trade=trade,
#                     notification_type=TradeNotification.NotificationType.TRADE_UPDATE,
#                     message=message,
#                     priority=priority
#                 )
#                 logger.info(f"Created notification for trade {trade.id} for user {self.user.id}")
#                 return notification
#         except Exception as e:
#             logger.error(f"Error creating notification: {str(e)}")
#             return None

#     async def send_json(self, data):
#         """Send JSON data to WebSocket."""
#         await self.send(text_data=json.dumps(data, cls=DecimalEncoder))

#     @db_sync_to_async
#     def _get_initial_trades(self, limit):
#         """Get the IDs of the first N trades created after subscription."""
#         try:
#             initial_trades = Trade.objects.filter(
#                 created_at__gte=self.subscription.start_date,
#                 plan_type__in=self.trade_manager.get_plan_levels(self.subscription.plan.name)
#             ).order_by('created_at')[:limit]
#             return [t.id for t in initial_trades]
#         except Exception as e:
#             logger.error(f"Error getting initial trades: {str(e)}")
#             return []
