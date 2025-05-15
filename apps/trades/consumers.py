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
        # Trade limits based on plan type
        self.company_limits = {
            'BASIC': {
                'new': 6,       # New trades after subscription
                'previous': 6,  # Trades active at subscription time
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
            
            # Get current trade counts
            trade_counts = await self._get_trade_counts()
            
            # Get plan limits based on subscription type
            plan_name = self.subscription.plan.name
            limits = self.company_limits.get(plan_name, {'new': None, 'previous': None, 'total': None})
            
            # Calculate remaining trades
            remaining = {
                'new': None if limits['new'] is None else max(0, limits['new'] - trade_counts['new']),
                'previous': None if limits['previous'] is None else max(0, limits['previous'] - trade_counts['previous']),
                'total': None if limits['total'] is None else max(0, limits['total'] - trade_counts['total'])
            }
            
            # Send subscription info
            await self.send(text_data=json.dumps({
                'type': 'subscription_info',
                'data': {
                    'plan': plan_name,
                    'start_date': self.subscription.start_date.isoformat(),
                    'end_date': self.subscription.end_date.isoformat(),
                    'limits': limits,
                    'current': trade_counts,
                    'remaining': remaining
                }
            }))
            
            return True

        except Exception as e:
            logger.error(f"Error setting up user group: {str(e)}")
            await self.send_error(4006, str(e))
            return False

    @db_sync_to_async
    def _get_trade_counts(self):
        """Get current trade counts for user based on subscription."""
        try:
            from apps.trades.models import Trade
            
            # Get plan type
            plan_name = self.subscription.plan.name
            plan_levels = self.trade_manager.get_plan_levels(plan_name)
            
            # Get subscription start date
            subscription_start = self.subscription.start_date
            
            # 1. Get "previous" trades - trades that were ACTIVE at subscription start time
            previous_trades = Trade.objects.filter(
                status='ACTIVE',
                created_at__lt=subscription_start,
                plan_type__in=plan_levels
            ).select_related('company').order_by('-created_at')
            
            # Count unique companies with previous trades
            previous_companies = set()
            for trade in previous_trades:
                previous_companies.add(trade.company.id)
            
            # 2. Get "new" trades - trades created AFTER subscription start time
            new_trades = Trade.objects.filter(
                created_at__gte=subscription_start,
                plan_type__in=plan_levels
            ).exclude(
                status='CANCELED'  # Exclude canceled trades
            ).select_related('company').order_by('-created_at')
            
            # Count unique companies with new trades
            new_companies = set()
            for trade in new_trades:
                new_companies.add(trade.company.id)
            
            # Ensure no company is counted in both categories
            for company_id in list(new_companies):
                if company_id in previous_companies:
                    previous_companies.remove(company_id)
            
            # Apply limits based on plan
            new_count = len(new_companies)
            previous_count = len(previous_companies)
            
            return {
                'new': new_count,
                'previous': previous_count,
                'total': new_count + previous_count
            }
            
        except Exception as e:
            logger.error(f"Error getting trade counts: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {'new': 0, 'previous': 0, 'total': 0}

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
        """Get filtered company data based on subscription plan and start date."""
        from apps.trades.models import Trade, Company
        from django.db.models import Prefetch
        
        try:
            with transaction.atomic():
                logger.info(f"Getting filtered company data for user {self.user.id}")
                
                # Get subscription details
                subscription_start = self.subscription.start_date
                plan_name = self.subscription.plan.name
                plan_levels = self.trade_manager.get_plan_levels(plan_name)
                
                # Step 1: Get all companies with any active or completed trades in accessible plan levels
                companies_with_trades = Company.objects.filter(
                    trades__status__in=['ACTIVE', 'COMPLETED'],
                    trades__plan_type__in=plan_levels
                ).distinct()
                
                # Step 2: Separate companies into "previous" and "new" collections
                previous_companies_data = []  # Companies with trades active at subscription start
                new_companies_data = []       # Companies with trades created after subscription start
                
                # Get all companies
                all_companies = list(companies_with_trades)
                
                # Process each company to categorize and format its data
                for company in all_companies:
                    # Get all trades for this company
                    company_trades = Trade.objects.filter(
                        company=company,
                        plan_type__in=plan_levels,
                        status__in=['ACTIVE', 'COMPLETED']
                    ).select_related('analysis').prefetch_related('history')
                    
                    # Check if this company had trades active at subscription start
                    pre_subscription_trades = [
                        t for t in company_trades 
                        if t.created_at < subscription_start and t.status == 'ACTIVE'
                    ]
                    
                    # Check if this company has new trades created after subscription start
                    post_subscription_trades = [
                        t for t in company_trades 
                        if t.created_at >= subscription_start
                    ]
                    
                    # If we have post-subscription trades, this is a "new" company
                    if post_subscription_trades:
                        # Find most recent intraday and positional trades for this company
                        intraday_trade = None
                        positional_trade = None
                        
                        # Sort trades by creation date (newest first)
                        sorted_trades = sorted(post_subscription_trades, key=lambda t: t.created_at, reverse=True)
                        
                        # Take the most recent trade of each type
                        for trade in sorted_trades:
                            if trade.trade_type == 'INTRADAY' and intraday_trade is None:
                                intraday_trade = trade
                            elif trade.trade_type == 'POSITIONAL' and positional_trade is None:
                                positional_trade = trade
                            
                            # Break if we've found both types
                            if intraday_trade and positional_trade:
                                break
                        
                        # Build company data for "new" category
                        company_data = {
                            'id': company.id,
                            'tradingSymbol': company.trading_symbol,
                            'exchange': company.exchange,
                            'instrumentName': self._get_instrument_name(company.instrument_type),
                            'intraday_trade': self._format_trade(intraday_trade) if intraday_trade else None,
                            'positional_trade': self._format_trade(positional_trade) if positional_trade else None,
                            'created_at': max([t.created_at for t in post_subscription_trades]).isoformat() if post_subscription_trades else None
                        }
                        new_companies_data.append(company_data)
                        
                    # If no post-subscription trades but had active trades at subscription time, it's a "previous" company
                    elif pre_subscription_trades:
                        # Find most recent intraday and positional trades for this company
                        intraday_trade = None
                        positional_trade = None
                        
                        # Sort trades by creation date (newest first)
                        sorted_trades = sorted(pre_subscription_trades, key=lambda t: t.created_at, reverse=True)
                        
                        # Take the most recent trade of each type
                        for trade in sorted_trades:
                            if trade.trade_type == 'INTRADAY' and intraday_trade is None:
                                intraday_trade = trade
                            elif trade.trade_type == 'POSITIONAL' and positional_trade is None:
                                positional_trade = trade
                            
                            # Break if we've found both types
                            if intraday_trade and positional_trade:
                                break
                        
                        # Build company data for "previous" category
                        company_data = {
                            'id': company.id,
                            'tradingSymbol': company.trading_symbol,
                            'exchange': company.exchange,
                            'instrumentName': self._get_instrument_name(company.instrument_type),
                            'intraday_trade': self._format_trade(intraday_trade) if intraday_trade else None,
                            'positional_trade': self._format_trade(positional_trade) if positional_trade else None,
                            'created_at': max([t.created_at for t in pre_subscription_trades]).isoformat() if pre_subscription_trades else None
                        }
                        previous_companies_data.append(company_data)
                
                # Sort both collections by created_at (newest first)
                new_companies_data.sort(key=lambda x: x['created_at'] if x['created_at'] else '', reverse=True)
                previous_companies_data.sort(key=lambda x: x['created_at'] if x['created_at'] else '', reverse=True)
                
                # Apply limits based on plan
                if plan_name == 'BASIC':
                    # For BASIC: 6 previous + 6 new
                    previous_companies_data = previous_companies_data[:6]
                    new_companies_data = new_companies_data[:6]
                elif plan_name == 'PREMIUM':
                    # For PREMIUM: 6 previous + 9 new
                    previous_companies_data = previous_companies_data[:6]
                    new_companies_data = new_companies_data[:9]
                # No limits for SUPER_PREMIUM and FREE_TRIAL
                
                logger.info(f"After filtering: {len(previous_companies_data)} previous companies, {len(new_companies_data)} new companies")
                
                # Calculate current counts
                current_counts = {
                    'new': len(new_companies_data),
                    'previous': len(previous_companies_data),
                    'total': len(new_companies_data) + len(previous_companies_data)
                }
                
                # Get plan limits
                plan_limits = self.company_limits.get(plan_name, {'new': None, 'previous': None, 'total': None})
                
                # Return structured data
                return {
                    'stock_data': new_companies_data + previous_companies_data,  # Combined list
                    'index_data': [],  # Include empty index_data as in the example
                    'subscription': {
                        'plan': plan_name,
                        'expires_at': self.subscription.end_date.isoformat(),
                        'limits': plan_limits,
                        'counts': current_counts
                    }
                }
                
        except Exception as e:
            logger.error(f"Error getting filtered company data: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'stock_data': [], 
                'index_data': [],
                'subscription': {
                    'plan': self.subscription.plan.name,
                    'expires_at': self.subscription.end_date.isoformat(),
                    'limits': self.company_limits.get(self.subscription.plan.name, 
                                                    {'new': None, 'previous': None, 'total': None}),
                    'counts': {'new': 0, 'previous': 0, 'total': 0}
                }
            }
    
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

            # Check if company is accessible based on subscription plan and timing
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
        from apps.trades.models import Trade, Company
        
        try:
            with transaction.atomic():
                # Get the trade and its associated company
                trade = Trade.objects.select_related(
                    'company', 'analysis'
                ).prefetch_related(
                    'history'
                ).get(id=trade_id)
                
                company = trade.company
                subscription_start = self.subscription.start_date
                plan_levels = self.trade_manager.get_plan_levels(self.subscription.plan.name)
                
                # Get trades for this company based on subscription timing
                active_trades = Trade.objects.filter(
                    company=company,
                    plan_type__in=plan_levels,
                    status__in=['ACTIVE', 'COMPLETED']
                ).select_related('analysis').prefetch_related('history')
                
                # Group trades by type
                intraday_trade = None
                positional_trade = None
                
                # Check if this trade was created after subscription start
                is_new_trade = trade.created_at >= subscription_start
                
                # Find the most recent trades based on trade category
                if is_new_trade:
                    # For new trades, only consider trades created after subscription
                    relevant_trades = [t for t in active_trades if t.created_at >= subscription_start]
                else:
                    # For previous trades, only consider trades active at subscription start
                    relevant_trades = [t for t in active_trades if t.created_at < subscription_start and t.status == 'ACTIVE']
                
                # Find most recent intraday and positional trades
                for t in sorted(relevant_trades, key=lambda x: x.created_at, reverse=True):
                    if t.trade_type == 'INTRADAY' and intraday_trade is None:
                        intraday_trade = t
                    elif t.trade_type == 'POSITIONAL' and positional_trade is None:
                        positional_trade = t
                    
                    # Break if we've found both types
                    if intraday_trade and positional_trade:
                        break
                
                # Format company data
                company_data = {
                    'id': company.id,
                    'tradingSymbol': company.trading_symbol,
                    'exchange': company.exchange,
                    'instrumentName': self._get_instrument_name(company.instrument_type),
                    'intraday_trade': self._format_trade(intraday_trade) if intraday_trade else None,
                    'positional_trade': self._format_trade(positional_trade) if positional_trade else None,
                    'created_at': max([t.created_at for t in relevant_trades]).isoformat() if relevant_trades else None
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
        """Check if the company is accessible based on subscription plan and timing."""
        from apps.trades.models import Company, Trade
        
        try:
            with transaction.atomic():
                # Get company
                company = Company.objects.get(id=company_id)
                
                # Get subscription details
                subscription_start = self.subscription.start_date
                plan_name = self.subscription.plan.name
                plan_levels = self.trade_manager.get_plan_levels(plan_name)
                
                # Check if this company has trades in the user's plan level
                trades = Trade.objects.filter(
                    company=company,
                    plan_type__in=plan_levels,
                    status__in=['ACTIVE', 'COMPLETED']
                )
                
                if not trades.exists():
                    logger.info(f"Company {company_id} has no trades in plan levels {plan_levels}")
                    return False
                
                # Categorize trades by subscription timing
                pre_subscription_trades = trades.filter(
                    created_at__lt=subscription_start,
                    status='ACTIVE'
                ).exists()
                
                post_subscription_trades = trades.filter(
                    created_at__gte=subscription_start
                ).exists()
                
                # Get plan limits
                limits = self.company_limits.get(plan_name, {'new': None, 'previous': None, 'total': None})
                
                # Count current numbers of companies
                trade_counts = self._get_trade_counts_sync()
                
                # If company has new trades, check against "new" limit
                if post_subscription_trades:
                    if limits['new'] is not None and trade_counts['new'] >= limits['new']:
                        # Check if this company is already in the user's new companies
                        is_in_new_companies = Trade.objects.filter(
                            company=company,
                            created_at__gte=subscription_start
                        ).exists()
                        
                        # Allow access if it's already in the user's list
                        return is_in_new_companies
                    
                    # No limit or under limit
                    return True
                    
                # If company has only previous trades, check against "previous" limit
                elif pre_subscription_trades:
                    if limits['previous'] is not None and trade_counts['previous'] >= limits['previous']:
                        # Check if this company is already in the user's previous companies
                        is_in_previous_companies = Trade.objects.filter(
                            company=company,
                            created_at__lt=subscription_start,
                            status='ACTIVE'
                        ).exists()
                        
                        # Allow access if it's already in the user's list
                        return is_in_previous_companies
                    
                    # No limit or under limit
                    return True
                
                # No applicable trades found
                return False
                
        except Company.DoesNotExist:
            logger.warning(f"Company {company_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error checking if company {company_id} is accessible: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _get_trade_counts_sync(self):
        """Synchronous version of _get_trade_counts for use within sync methods."""
        try:
            from apps.trades.models import Trade
            
            # Get plan type
            plan_name = self.subscription.plan.name
            plan_levels = self.trade_manager.get_plan_levels(plan_name)
            
            # Get subscription start date
            subscription_start = self.subscription.start_date
            
            # 1. Get "previous" trades - trades that were ACTIVE at subscription start time
            previous_trades = Trade.objects.filter(
                status='ACTIVE',
                created_at__lt=subscription_start,
                plan_type__in=plan_levels
            ).select_related('company')
            
            # Count unique companies with previous trades
            previous_companies = set()
            for trade in previous_trades:
                previous_companies.add(trade.company.id)
            
            # 2. Get "new" trades - trades created AFTER subscription start time
            new_trades = Trade.objects.filter(
                created_at__gte=subscription_start,
                plan_type__in=plan_levels
            ).exclude(
                status='CANCELED'  # Exclude canceled trades
            ).select_related('company')
            
            # Count unique companies with new trades
            new_companies = set()
            for trade in new_trades:
                new_companies.add(trade.company.id)
            
            # Ensure no company is counted in both categories
            for company_id in list(new_companies):
                if company_id in previous_companies:
                    previous_companies.remove(company_id)
            
            # Return counts
            new_count = len(new_companies)
            previous_count = len(previous_companies)
            
            return {
                'new': new_count,
                'previous': previous_count,
                'total': new_count + previous_count
            }
            
        except Exception as e:
            logger.error(f"Error getting trade counts sync: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {'new': 0, 'previous': 0, 'total': 0}

    async def receive(self, text_data):
        """Handle messages sent from the WebSocket client."""
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            if action == 'ping':
                # Simple keepalive mechanism
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': timezone.now().isoformat()
                }))
            elif action == 'refresh':
                # Client requested data refresh
                await self.send_initial_data()
            elif action == 'subscription_info':
                # Send subscription info
                trade_counts = await self._get_trade_counts()
                plan_name = self.subscription.plan.name
                limits = self.company_limits.get(plan_name, {'new': None, 'previous': None, 'total': None})
                
                # Calculate remaining trades
                remaining = {
                    'new': None if limits['new'] is None else max(0, limits['new'] - trade_counts['new']),
                    'previous': None if limits['previous'] is None else max(0, limits['previous'] - trade_counts['previous']),
                    'total': None if limits['total'] is None else max(0, limits['total'] - trade_counts['total'])
                }
                
                await self.send(text_data=json.dumps({
                    'type': 'subscription_info',
                    'data': {
                        'plan': plan_name,
                        'start_date': self.subscription.start_date.isoformat(),
                        'end_date': self.subscription.end_date.isoformat(),
                        'limits': limits,
                        'current': trade_counts,
                        'remaining': remaining
                    }
                }))
            else:
                logger.warning(f"Unknown action received: {action}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f"Unknown action: {action}"
                }))
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': "Invalid JSON format"
            }))
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': "Error processing your request"
            }))

    async def system_notification(self, event):
        """Handle system notifications to be sent to the client."""
        if not self.is_connected:
            return
            
        try:
            message = event.get('message')
            notification_type = event.get('notification_type', 'info')
            
            await self.send(text_data=json.dumps({
                'type': 'system_notification',
                'notification_type': notification_type,
                'message': message
            }))
        except Exception as e:
            logger.error(f"Error sending system notification: {str(e)}")


class IndexUpdateManager:
    """Utility class for managing index data updates."""
    
    @staticmethod
    async def get_cached_indices():
        """Get cached index data."""
        try:
            return await sync_to_async(cache.get)('cached_indices')
        except Exception as e:
            logger.error(f"Failed to get cached indices: {str(e)}")
            return None

    @staticmethod
    async def set_cached_indices(data):
        """Store index data in cache."""
        try:
            await sync_to_async(cache.set)('cached_indices', data, 3600)  # 1 hour
        except Exception as e:
            logger.error(f"Failed to set cached indices: {str(e)}")


class IndexUpdatesConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for delivering real-time index updates."""
    
    async def connect(self):
        """Handle WebSocket connection establishment."""
        await self.accept()
        
        # Add to index updates group
        await self.channel_layer.group_add('index_updates', self.channel_name)
        
        # Send initial index data
        await self.send_initial_indices()
        
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        await self.channel_layer.group_discard('index_updates', self.channel_name)
    
    async def send_initial_indices(self):
        """Send initial index data to client."""
        try:
            # Get cached indices or fetch new ones
            indices = await IndexUpdateManager.get_cached_indices()
            
            if not indices:
                # In a real implementation, you would fetch from database or external service
                indices = await self._fetch_index_data()
                await IndexUpdateManager.set_cached_indices(indices)
                
            await self.send(text_data=json.dumps({
                'type': 'initial_indices',
                'data': indices
            }, cls=DecimalEncoder))
            
        except Exception as e:
            logger.error(f"Error sending initial indices: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to load index data'
            }))
    
    async def _fetch_index_data(self):
        """Fetch index data from database or external service."""
        # This would be implemented based on your specific data sources
        # Placeholder implementation
        return [
            {
                'id': 'nifty50',
                'name': 'NIFTY 50',
                'value': '20123.45',
                'change': '142.50',
                'change_percent': '0.71',
                'trend': 'up',
                'updated_at': timezone.now().isoformat()
            },
            {
                'id': 'sensex',
                'name': 'SENSEX',
                'value': '65789.12',
                'change': '456.78',
                'change_percent': '0.69',
                'trend': 'up',
                'updated_at': timezone.now().isoformat()
            }
        ]
    
    async def index_update(self, event):
        """Handle index update messages."""
        try:
            data = event['data']
            await self.send(text_data=json.dumps({
                'type': 'index_update',
                'data': data
            }, cls=DecimalEncoder))
        except Exception as e:
            logger.error(f"Error sending index update: {str(e)}")











# from channels.generic.websocket import AsyncWebsocketConsumer
# from asgiref.sync import sync_to_async
# from django.core.cache import cache
# from typing import Dict, List, Optional
# import json
# from decimal import Decimal
# import logging
# import asyncio
# from urllib.parse import parse_qs
# from django.utils import timezone
# from rest_framework_simplejwt.authentication import JWTAuthentication
# from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
# from django.db import transaction
# from apps.subscriptions.models import Subscription
# from apps.trades.models import Trade

# logger = logging.getLogger(__name__)

# # Database-specific sync_to_async decorator
# db_sync_to_async = sync_to_async(thread_sensitive=True)

# class DecimalEncoder(json.JSONEncoder):
#     """Custom JSON encoder to handle Decimal objects."""
#     def default(self, obj):
#         if isinstance(obj, Decimal):
#             return str(obj)
#         return super().default(obj)

# class TradeUpdateManager:
#     """Utility class for managing trade caching and plan level access."""
    
#     CACHE_TIMEOUT = 3600  # Cache duration in seconds (1 hour)
    
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
#     def get_plan_levels(plan_type: str) -> List[str]:
#         """Get accessible plan levels for a given plan type."""
#         return {
#             'BASIC': ['BASIC'],
#             'PREMIUM': ['BASIC', 'PREMIUM'],
#             'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM'],
#             'FREE_TRIAL': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
#         }.get(plan_type, [])

# class TradeUpdatesConsumer(AsyncWebsocketConsumer):
#     """WebSocket consumer for delivering real-time trade updates to authenticated users."""
    
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
#         self.user_group = None
#         self._initial_data_task = None
#         # Trade limits based on plan type (now counting companies, not individual trades)
#         self.company_limits = {
#             'BASIC': {
#                 'new': 6,
#                 'previous': 6,
#                 'total': 12
#             },
#             'PREMIUM': {
#                 'new': 9,
#                 'previous': 6,
#                 'total': 15
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
#         """Handle WebSocket connection establishment."""
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
#             # Try to get token from URL parameters first
#             token = self.scope['url_route']['kwargs'].get('token')
            
#             # If not in URL, try query parameters
#             if not token:
#                 query_string = self.scope.get('query_string', b'').decode('utf-8')
#                 parsed_qs = parse_qs(query_string)
#                 token = parsed_qs.get('token', [None])[0] or parsed_qs.get('access_token', [None])[0]

#             if not token:
#                 await self.send_error(4001)
#                 return False

#             # Authenticate using the token
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
#             from apps.subscriptions.models import Subscription
            
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

#             # Set up user group
#             self.user_group = f"trade_updates_{self.user.id}"
            
#             # Add to channel group
#             await self.channel_layer.group_add(self.user_group, self.channel_name)
#             logger.info(f"Added user {self.user.id} to group {self.user_group}")
            
#             # Get current trade counts
#             trade_counts = await self._get_trade_counts()
            
#             # Calculate remaining trades
#             plan_limits = {
#                 'BASIC': {'new': 6, 'previous': 6, 'total': 12},
#                 'PREMIUM': {'new': 9, 'previous': 6, 'total': 15},
#                 'SUPER_PREMIUM': {'new': None, 'previous': None, 'total': None},
#                 'FREE_TRIAL': {'new': None, 'previous': None, 'total': None}
#             }
            
#             limits = plan_limits.get(self.subscription.plan.name, {'new': None, 'previous': None, 'total': None})
            
#             # Calculate remaining trades
#             remaining = {
#                 'new': None if limits['new'] is None else max(0, limits['new'] - trade_counts['new']),
#                 'previous': None if limits['previous'] is None else max(0, limits['previous'] - trade_counts['previous']),
#                 'total': None if limits['total'] is None else max(0, limits['total'] - trade_counts['total'])
#             }
            
#             # Send subscription info
#             await self.send(text_data=json.dumps({
#                 'type': 'subscription_info',
#                 'data': {
#                     'plan': self.subscription.plan.name,
#                     'start_date': self.subscription.start_date.isoformat(),
#                     'end_date': self.subscription.end_date.isoformat(),
#                     'limits': limits,
#                     'current': trade_counts,
#                     'remaining': remaining
#                 }
#             }))
            
#             return True

#         except Exception as e:
#             logger.error(f"Error setting up user group: {str(e)}")
#             await self.send_error(4006, str(e))
#             return False

#     @db_sync_to_async
#     def _get_trade_counts(self):
#         """Get current trade counts for the user."""
#         try:
#             from .models import Trade
            
#             # Get plan limits
#             plan_limits = {
#                 'BASIC': {'new': 6, 'previous': 6},
#                 'PREMIUM': {'new': 9, 'previous': 6},
#                 'SUPER_PREMIUM': {'new': None, 'previous': None},
#                 'FREE_TRIAL': {'new': None, 'previous': None}
#             }
            
#             limits = plan_limits.get(self.subscription.plan.name, {'new': None, 'previous': None})
            
#             # Get new trades (after subscription) - limited to plan limit
#             new_trades = Trade.objects.filter(
#                 created_at__gte=self.subscription.start_date,
#                 status__in=['ACTIVE', 'COMPLETED'],
#                 plan_type__in=self.trade_manager.get_plan_levels(self.subscription.plan.name)
#             ).order_by('created_at')
            
#             # Apply limit for new trades
#             if limits['new'] is not None:
#                 new_trades = new_trades[:limits['new']]
#             new_count = new_trades.count()
            
#             # Get previous trades (before subscription)
#             # First get trades that were active at subscription time
#             previous_trades = Trade.objects.filter(
#                 created_at__lt=self.subscription.start_date,
#                 plan_type__in=self.trade_manager.get_plan_levels(self.subscription.plan.name)
#             ).order_by('created_at')[:6]  # Limit to 6 trades
            
#             # Count trades that are either:
#             # 1. Still active, or
#             # 2. Were completed after subscription date
#             previous_count = 0
#             for trade in previous_trades:
#                 if trade.status == 'ACTIVE' or (
#                     trade.status == 'COMPLETED' and 
#                     trade.completed_at and 
#                     trade.completed_at >= self.subscription.start_date
#                 ):
#                     previous_count += 1
            
#             return {
#                 'new': new_count,
#                 'previous': previous_count,
#                 'total': new_count + previous_count
#             }
            
#         except Exception as e:
#             logger.error(f"Error getting trade counts: {str(e)}")
#             return {'new': 0, 'previous': 0, 'total': 0}

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

#     @db_sync_to_async
#     def _get_filtered_company_data(self):
#         """Get filtered and grouped company data based on subscription plan."""
#         from .models import Trade, Company
#         from django.db.models import Prefetch
        
#         try:
#             with transaction.atomic():
#                 logger.info(f"Getting filtered company data for user {self.user.id}")
                
#                 # Get plan levels accessible to this user
#                 plan_levels = self.trade_manager.get_plan_levels(self.subscription.plan.name)
                
#                 # Get company limits based on plan
#                 limits = self.company_limits.get(self.subscription.plan.name, {'new': None, 'previous': None})
                
#                 # Get all companies with active trades
#                 all_companies = Company.objects.prefetch_related(
#                     Prefetch(
#                         'trades',
#                         queryset=Trade.objects.filter(
#                             status__in=['ACTIVE', 'COMPLETED'],  # Include both active and completed trades
#                             plan_type__in=plan_levels
#                         ).select_related('analysis').prefetch_related('history'),
#                         to_attr='filtered_trades'
#                     )
#                 ).filter(
#                     trades__status__in=['ACTIVE', 'COMPLETED'],
#                     trades__plan_type__in=plan_levels
#                 ).distinct()
                
#                 # Separate companies into new and previous based on subscription date
#                 previous_companies = []  # Companies with trades before subscription
#                 new_companies = []       # Companies with trades after subscription
                
#                 # Process each company
#                 company_list = list(all_companies)
#                 for company in company_list:
#                     # Group trades by type (intraday/positional) and keep only the most recent of each
#                     intraday_trade = None
#                     positional_trade = None
                    
#                     active_trades = company.filtered_trades
                    
#                     # Check if there are any trades after subscription date
#                     post_subscription_trades = [
#                         t for t in active_trades 
#                         if t.created_at >= self.subscription.start_date
#                     ]
                    
#                     # Check if there are any trades before subscription date
#                     pre_subscription_trades = [
#                         t for t in active_trades 
#                         if t.created_at < self.subscription.start_date
#                     ]
                    
#                     # If company has trades after subscription, add to new companies
#                     if post_subscription_trades:
#                         # Find most recent intraday and positional trades
#                         for trade in sorted(post_subscription_trades, key=lambda t: t.created_at, reverse=True):
#                             if trade.trade_type == 'INTRADAY' and intraday_trade is None:
#                                 intraday_trade = trade
#                             elif trade.trade_type == 'POSITIONAL' and positional_trade is None:
#                                 positional_trade = trade
                            
#                             # Break if we've found both types
#                             if intraday_trade and positional_trade:
#                                 break
                        
#                         # Build company data structure
#                         company_data = {
#                             'id': company.id,
#                             'tradingSymbol': company.trading_symbol,
#                             'exchange': company.exchange,
#                             'instrumentName': self._get_instrument_name(company.instrument_type),
#                             'intraday_trade': self._format_trade(intraday_trade) if intraday_trade else None,
#                             'positional_trade': self._format_trade(positional_trade) if positional_trade else None,
#                             'created_at': max([t.created_at for t in post_subscription_trades]).isoformat() if post_subscription_trades else None
#                         }
#                         new_companies.append(company_data)
                    
#                     # If company has trades before subscription, add to previous companies
#                     elif pre_subscription_trades:
#                         # Find most recent intraday and positional trades
#                         for trade in sorted(pre_subscription_trades, key=lambda t: t.created_at, reverse=True):
#                             if trade.trade_type == 'INTRADAY' and intraday_trade is None:
#                                 intraday_trade = trade
#                             elif trade.trade_type == 'POSITIONAL' and positional_trade is None:
#                                 positional_trade = trade
                            
#                             # Break if we've found both types
#                             if intraday_trade and positional_trade:
#                                 break
                        
#                         # Build company data structure
#                         company_data = {
#                             'id': company.id,
#                             'tradingSymbol': company.trading_symbol,
#                             'exchange': company.exchange,
#                             'instrumentName': self._get_instrument_name(company.instrument_type),
#                             'intraday_trade': self._format_trade(intraday_trade) if intraday_trade else None,
#                             'positional_trade': self._format_trade(positional_trade) if positional_trade else None,
#                             'created_at': max([t.created_at for t in pre_subscription_trades]).isoformat() if pre_subscription_trades else None
#                         }
#                         previous_companies.append(company_data)
                
#                 # Sort companies by created_at date (most recent first)
#                 new_companies.sort(key=lambda x: x['created_at'] if x['created_at'] else '', reverse=True)
#                 previous_companies.sort(key=lambda x: x['created_at'] if x['created_at'] else '', reverse=True)
                
#                 # Apply strict limits based on plan type
#                 if self.subscription.plan.name == 'BASIC':
#                     # For BASIC: 6 previous + 6 new
#                     previous_companies = previous_companies[:6]
#                     new_companies = new_companies[:6]
#                 elif self.subscription.plan.name == 'PREMIUM':
#                     # For PREMIUM: 6 previous + 9 new
#                     previous_companies = previous_companies[:6]
#                     new_companies = new_companies[:9]
#                 # SUPER_PREMIUM and FREE_TRIAL have no limits
                
#                 logger.info(f"After filtering: {len(previous_companies)} previous companies, {len(new_companies)} new companies")
                
#                 # Calculate subscription counts
#                 subscription_counts = {
#                     'new': len(new_companies),
#                     'previous': len(previous_companies),
#                     'total': len(new_companies) + len(previous_companies)
#                 }
                
#                 # Return structured data with subscription info
#                 return {
#                     'stock_data': new_companies + previous_companies,
#                     'index_data': [],  # Include empty index_data as in your example
#                     'subscription': {
#                         'plan': self.subscription.plan.name,
#                         'expires_at': self.subscription.end_date.isoformat(),
#                         'limits': {
#                             'new': 9 if self.subscription.plan.name == 'PREMIUM' else 6,
#                             'previous': 6,
#                             'total': 15 if self.subscription.plan.name == 'PREMIUM' else 12
#                         },
#                         'counts': subscription_counts
#                     }
#                 }
                
#         except Exception as e:
#             logger.error(f"Error getting filtered company data: {str(e)}")
#             import traceback
#             logger.error(traceback.format_exc())
#             return {
#                 'stock_data': [], 
#                 'index_data': [],
#                 'subscription': {
#                     'plan': self.subscription.plan.name,
#                     'expires_at': self.subscription.end_date.isoformat(),
#                     'limits': {
#                         'new': 9 if self.subscription.plan.name == 'PREMIUM' else 6,
#                         'previous': 6,
#                         'total': 15 if self.subscription.plan.name == 'PREMIUM' else 12
#                     },
#                     'counts': {'new': 0, 'previous': 0, 'total': 0}
#                 }
#             }
    
#     def _get_instrument_name(self, instrument_type):
#         """Map instrument type to display name."""
#         instrument_mapping = {
#             'EQUITY': 'EQUITY',
#             'FNO_FUT': 'F&O',
#             'FNO_CE': 'F&O',
#             'FNO_PE': 'F&O',
#         }
#         return instrument_mapping.get(instrument_type, instrument_type)
    
#     def _format_trade(self, trade):
#         """Format trade data for WebSocket response."""
#         if not trade:
#             return None
            
#         try:
#             formatted_trade = {
#                 'id': trade.id,
#                 'trade_type': trade.trade_type,
#                 'status': trade.status,
#                 'plan_type': trade.plan_type,
#                 'warzone': str(trade.warzone),
#                 'image': trade.image.url if trade.image else None,
#                 'warzone_history': trade.warzone_history or [],
#                 'analysis': None,
#                 'trade_history': []
#             }

#             # Add analysis data if available
#             if hasattr(trade, 'analysis') and trade.analysis:
#                 formatted_trade['analysis'] = {
#                     'bull_scenario': trade.analysis.bull_scenario,
#                     'bear_scenario': trade.analysis.bear_scenario,
#                     'status': trade.analysis.status,
#                     'completed_at': trade.analysis.completed_at.isoformat() if trade.analysis.completed_at else None,
#                     'created_at': trade.analysis.created_at.isoformat(),
#                     'updated_at': trade.analysis.updated_at.isoformat()
#                 }

#             # Add trade history if available
#             if hasattr(trade, 'history'):
#                 history_items = list(trade.history.all())
#                 formatted_trade['trade_history'] = []
                
#                 for history in history_items:
#                     history_item = {
#                         'buy': str(history.buy),
#                         'target': str(history.target),
#                         'sl': str(history.sl),
#                         'timestamp': history.timestamp.isoformat(),
#                     }
                    
#                     # Add risk/reward metrics if they exist
#                     if hasattr(history, 'risk_reward_ratio'):
#                         history_item['risk_reward_ratio'] = str(history.risk_reward_ratio)
                    
#                     if hasattr(history, 'potential_profit_percentage'):
#                         history_item['potential_profit_percentage'] = str(history.potential_profit_percentage)
                    
#                     if hasattr(history, 'stop_loss_percentage'):
#                         history_item['stop_loss_percentage'] = str(history.stop_loss_percentage)
                    
#                     formatted_trade['trade_history'].append(history_item)

#             return formatted_trade
            
#         except Exception as e:
#             logger.error(f"Error formatting trade {trade.id}: {str(e)}")
#             return None

#     async def send_initial_data(self):
#         """Send initial trade data to the client."""
#         try:
#             data = await self._get_filtered_company_data()
#             logger.info(f"Sending initial data with {len(data['stock_data'])} companies")
            
#             await self.send(text_data=json.dumps({
#                 'type': 'initial_data',
#                 'stock_data': data['stock_data'],
#                 'index_data': data['index_data']
#             }, cls=DecimalEncoder))
            
#             await self.send_success("initial_data")
            
#         except asyncio.CancelledError:
#             logger.debug("Initial data task cancelled")
#         except Exception as e:
#             logger.error(f"Error sending initial data: {str(e)}")
#             await self.send_error(4006, str(e))

#     async def trade_update(self, event):
#         """Handle trade update messages."""
#         logger.info(f"WS consumer received trade_update event: {event}")
#         try:
#             if not self.is_connected or not self.subscription:
#                 logger.warning("Consumer not connected or no subscription")
#                 return

#             data = event["data"]
#             logger.info(f"Processing trade update for trade_id: {data['trade_id']}")
            
#             # Get updated company data that contains this trade
#             updated_company = await self._get_company_with_trade(data["trade_id"])
#             if not updated_company:
#                 logger.warning(f"Company with trade {data['trade_id']} not found")
#                 return

#             # Check if the company is accessible based on subscription limits
#             if not await self._is_company_accessible(updated_company['id']):
#                 logger.warning(f"Company {updated_company['id']} not accessible to user {self.user.id}")
#                 return
            
#             # Prepare response data
#             response_data = {
#                 "type": "trade_update",
#                 "data": {
#                     "updated_company": updated_company,
#                     "subscription": {
#                         "plan": self.subscription.plan.name,
#                         "expires_at": self.subscription.end_date.isoformat(),
#                         "limits": self.company_limits.get(self.subscription.plan.name, 
#                                                          {'new': None, 'previous': None, 'total': None})
#                     }
#                 }
#             }

#             logger.info("Sending trade update to WebSocket")
#             await self.send(text_data=json.dumps(response_data, cls=DecimalEncoder))
#             logger.info("Trade update sent successfully")

#         except Exception as e:
#             logger.error(f"Error handling trade update: {str(e)}")
#             import traceback
#             logger.error(traceback.format_exc())
#             await self.send(text_data=json.dumps({
#                 "type": "error",
#                 "data": {
#                     "message": "Error processing trade update",
#                     "error": str(e)
#                 }
#             }, cls=DecimalEncoder))

#     @db_sync_to_async
#     def _get_company_with_trade(self, trade_id):
#         """Get company data that contains the specified trade."""
#         from .models import Trade, Company
        
#         try:
#             with transaction.atomic():
#                 # Get the trade and its associated company
#                 trade = Trade.objects.select_related(
#                     'company', 'analysis'
#                 ).prefetch_related(
#                     'history'
#                 ).get(id=trade_id)
                
#                 company = trade.company
                
#                 # Get all active trades for this company
#                 active_trades = Trade.objects.filter(
#                     company=company,
#                     status='ACTIVE',
#                     plan_type__in=self.trade_manager.get_plan_levels(self.subscription.plan.name)
#                 ).select_related('analysis').prefetch_related('history')
                
#                 # Group by trade type
#                 intraday_trade = None
#                 positional_trade = None
                
#                 for t in active_trades:
#                     if t.trade_type == 'INTRADAY' and (intraday_trade is None or t.created_at > intraday_trade.created_at):
#                         intraday_trade = t
#                     elif t.trade_type == 'POSITIONAL' and (positional_trade is None or t.created_at > positional_trade.created_at):
#                         positional_trade = t
                
#                 # Format company data
#                 company_data = {
#                     'id': company.id,
#                     'tradingSymbol': company.trading_symbol,
#                     'exchange': company.exchange,
#                     'instrumentName': self._get_instrument_name(company.instrument_type),
#                     'intraday_trade': self._format_trade(intraday_trade) if intraday_trade else None,
#                     'positional_trade': self._format_trade(positional_trade) if positional_trade else None,
#                     'created_at': max([t.created_at for t in active_trades]).isoformat() if active_trades else None
#                 }
                
#                 return company_data
                
#         except Trade.DoesNotExist:
#             logger.warning(f"Trade {trade_id} not found")
#             return None
#         except Exception as e:
#             logger.error(f"Error getting company with trade {trade_id}: {str(e)}")
#             import traceback
#             logger.error(traceback.format_exc())
#             return None

#     @db_sync_to_async
#     def _is_company_accessible(self, company_id):
#         """Check if user has access to the company based on subscription limits."""
#         from .models import Company, Trade
        
#         try:
#             with transaction.atomic():
#                 if not self.subscription:
#                     return False
                    
#                 # For SUPER_PREMIUM and FREE_TRIAL, all companies are accessible
#                 if self.subscription.plan.name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
#                     return True
                
#                 # Get accessible plan levels
#                 plan_levels = self.trade_manager.get_plan_levels(self.subscription.plan.name)
                
#                 # Find this company's position in the list of all companies
#                 company = Company.objects.get(id=company_id)
                
#                 # Check if company has any trades created after subscription
#                 has_post_subscription_trades = Trade.objects.filter(
#                     company=company,
#                     created_at__gte=self.subscription.start_date,
#                     status='ACTIVE',
#                     plan_type__in=plan_levels
#                 ).exists()
                
#                 if has_post_subscription_trades:
#                     # Get all companies with post-subscription trades
#                     companies_with_post_trades = Company.objects.filter(
#                         trades__created_at__gte=self.subscription.start_date,
#                         trades__status='ACTIVE',
#                         trades__plan_type__in=plan_levels
#                     ).distinct().order_by('trades__created_at')
                    
#                     # Check if this company is within the limit
#                     company_position = list(companies_with_post_trades).index(company) if company in companies_with_post_trades else -1
                    
#                     if company_position == -1:
#                         return False
                        
#                     # Get limit for new companies
#                     new_limit = self.company_limits.get(self.subscription.plan.name, {}).get('new')
#                     if new_limit is None:  # No limit
#                         return True
                        
#                     return company_position < new_limit
#                 else:
#                     # Check for pre-subscription trades
#                     has_pre_subscription_trades = Trade.objects.filter(
#                         company=company,
#                         created_at__lt=self.subscription.start_date,
#                         status='ACTIVE',
#                         plan_type__in=plan_levels
#                     ).exists()
                    
#                     if not has_pre_subscription_trades:
#                         return False
                        
#                     # Get all companies with pre-subscription trades
#                     companies_with_pre_trades = Company.objects.filter(
#                         trades__created_at__lt=self.subscription.start_date,
#                         trades__status='ACTIVE',
#                         trades__plan_type__in=plan_levels
#                     ).distinct().order_by('trades__created_at')
                    
#                     # Check if this company is within the limit
#                     company_position = list(companies_with_pre_trades).index(company) if company in companies_with_pre_trades else -1
                    
#                     if company_position == -1:
#                         return False
                        
#                     # Get limit for previous companies
#                     previous_limit = self.company_limits.get(self.subscription.plan.name, {}).get('previous')
#                     if previous_limit is None:  # No limit
#                         return True
                        
#                     return company_position < previous_limit
                    
#         except Exception as e:
#             logger.error(f"Error checking company access: {str(e)}")
#             import traceback
#             logger.error(traceback.format_exc())
#             return False
