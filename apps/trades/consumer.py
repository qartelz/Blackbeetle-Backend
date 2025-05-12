from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from apps.subscriptions.models import Subscription
from .models import Trade, Company
from apps.notifications.models import TradeNotification, NotificationPreference
from django.core.exceptions import ObjectDoesNotExist
import json
import logging
from datetime import datetime
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()

class TradeUpdatesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        """Handle WebSocket connection."""
        try:
            # Get user from scope (set by authentication middleware)
            self.user = self.scope["user"]
            if not self.user.is_authenticated:
                logger.warning(f"Unauthenticated connection attempt")
                await self.close()
                return

            # Get user's subscription
            self.subscription = await self.get_user_subscription()
            if not self.subscription:
                logger.warning(f"No active subscription found for user {self.user.id}")
                await self.close()
                return

            # Create notification preferences if they don't exist
            await self.ensure_notification_preferences()

            # Join user's trade updates group
            self.group_name = f"trade_updates_{self.user.id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()

            # Send initial trade data
            await self.send_initial_trades()
            logger.info(f"WebSocket connection established for user {self.user.id}")

        except Exception as e:
            logger.error(f"Error in WebSocket connection: {str(e)}")
            await self.close()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        try:
            if hasattr(self, 'group_name'):
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
                logger.info(f"WebSocket disconnected for user {self.user.id}")
        except Exception as e:
            logger.error(f"Error in WebSocket disconnection: {str(e)}")

    @database_sync_to_async
    def get_user_subscription(self):
        """Get user's active subscription."""
        try:
            return Subscription.objects.select_related('plan').get(
                user=self.user,
                is_active=True,
                start_date__lte=timezone.now(),
                end_date__gte=timezone.now()
            )
        except Subscription.DoesNotExist:
            return None

    @database_sync_to_async
    def ensure_notification_preferences(self):
        """Ensure user has notification preferences."""
        NotificationPreference.objects.get_or_create(
            user=self.user,
            defaults={
                'enable_trade_updates': True,
                'enable_realtime_updates': True
            }
        )

    @database_sync_to_async
    def get_initial_trades(self):
        """Get initial trades based on subscription level."""
        try:
            trades = Trade.get_trades_for_subscription(self.user, self.subscription)
            return trades.select_related(
                'company',
                'analysis'
            ).prefetch_related(
                'history'
            )
        except Exception as e:
            logger.error(f"Error fetching initial trades: {str(e)}")
            return []

    async def send_initial_trades(self):
        """Send initial trade data to the client."""
        try:
            trades = await self.get_initial_trades()
            formatted_trades = []

            for trade in trades:
                try:
                    trade_data = {
                        "id": trade.id,
                        "company": {
                            "id": trade.company.id,
                            "trading_symbol": trade.company.trading_symbol,
                            "exchange": trade.company.exchange,
                            "instrument_type": trade.company.instrument_type
                        },
                        "trade_type": trade.trade_type,
                        "status": trade.status,
                        "plan_type": trade.plan_type,
                        "warzone": str(trade.warzone),
                        "image": trade.image.url if trade.image else None,
                        "warzone_history": trade.warzone_history or [],
                        "created_at": trade.created_at.isoformat(),
                        "updated_at": trade.updated_at.isoformat()
                    }

                    # Add analysis data if exists
                    if hasattr(trade, 'analysis'):
                        trade_data["analysis"] = {
                            "bull_scenario": trade.analysis.bull_scenario or "",
                            "bear_scenario": trade.analysis.bear_scenario or "",
                            "status": trade.analysis.status,
                            "completed_at": trade.analysis.completed_at.isoformat() if trade.analysis.completed_at else None
                        }

                    # Add trade history
                    trade_data["trade_history"] = [{
                        "buy": str(history.buy),
                        "target": str(history.target),
                        "sl": str(history.sl),
                        "timestamp": history.timestamp.isoformat(),
                        "risk_reward_ratio": str(history.risk_reward_ratio),
                        "potential_profit_percentage": str(history.potential_profit_percentage),
                        "stop_loss_percentage": str(history.stop_loss_percentage)
                    } for history in trade.history.all()]

                    formatted_trades.append(trade_data)

                except Exception as e:
                    logger.error(f"Error formatting trade {trade.id}: {str(e)}")
                    continue

            await self.send_json({
                "type": "initial_trades",
                "data": {
                    "trades": formatted_trades,
                    "subscription": {
                        "plan": self.subscription.plan.name,
                        "expires_at": self.subscription.end_date.isoformat()
                    }
                }
            })
            logger.info(f"Sent initial trades to user {self.user.id}")

        except Exception as e:
            logger.error(f"Error sending initial trades: {str(e)}")
            await self.send_json({
                "type": "error",
                "data": {
                    "message": "Error loading trades. Please refresh the page."
                }
            })

    async def trade_update(self, event):
        """Handle trade update messages."""
        try:
            data = event["data"]
            trade = await self.get_trade(data["trade_id"])
            
            if not trade or not await self.is_trade_accessible(trade):
                return

            # Create notification
            await self.create_notification(trade, data)

            # Send update to client
            await self.send_json({
                "type": "trade_update",
                "data": data
            })

        except Exception as e:
            logger.error(f"Error handling trade update: {str(e)}")

    @database_sync_to_async
    def get_trade(self, trade_id):
        """Get trade by ID."""
        try:
            return Trade.objects.select_related('company').get(id=trade_id)
        except Trade.DoesNotExist:
            return None

    @database_sync_to_async
    def is_trade_accessible(self, trade):
        """Check if user has access to the trade."""
        return trade.is_accessible_to_user(self.user)

    @database_sync_to_async
    def create_notification(self, trade, data):
        """Create a notification for the trade update."""
        try:
            message = f"Trade update for {trade.company.trading_symbol}: {data.get('action', 'updated')}"
            priority = TradeNotification.Priority.HIGH if data.get("trade_status") == Trade.Status.ACTIVE else TradeNotification.Priority.NORMAL
            
            return TradeNotification.create_trade_notification(
                user=self.user,
                trade=trade,
                notification_type=TradeNotification.NotificationType.TRADE_UPDATE,
                message=message,
                priority=priority
            )
        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            return None

    async def notification(self, event):
        """Handle notification messages."""
        await self.send_json({
            "type": "notification",
            "data": event["data"]
        }) 