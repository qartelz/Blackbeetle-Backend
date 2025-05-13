from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from apps.subscriptions.models import Subscription
from .models import Trade
from apps.notifications.models import TradeNotification, NotificationPreference
import json
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class TradeUpdatesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return

        # Get user's subscription
        self.subscription = await self.get_user_subscription()
        if not self.subscription:
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

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def get_user_subscription(self):
        """Get user's active subscription."""
        return Subscription.objects.filter(
            user=self.user,
            is_active=True
        ).first()

    @database_sync_to_async
    def ensure_notification_preferences(self):
        """Ensure user has notification preferences."""
        NotificationPreference.objects.get_or_create(user=self.user)

    @database_sync_to_async
    def get_initial_trades(self):
        """Get initial trades based on subscription level."""
        return Trade.get_trades_for_subscription(self.user, self.subscription)

    async def send_initial_trades(self):
        """Send initial trade data to the client."""
        trades = await self.get_initial_trades()
        await self.send_json({
            "type": "initial_trades",
            "data": {
                "trades": [
                    {
                        "id": trade.id,
                        "company": {
                            "id": trade.company.id,
                            "trading_symbol": trade.company.trading_symbol,
                            "exchange": trade.company.exchange
                        },
                        "trade_type": trade.trade_type,
                        "status": trade.status,
                        "plan_type": trade.plan_type,
                        "warzone": str(trade.warzone),
                        "image": trade.image.url if trade.image else None,
                        "warzone_history": trade.warzone_history,
                        "analysis": {
                            "bull_scenario": trade.analysis.bull_scenario if hasattr(trade, 'analysis') else "",
                            "bear_scenario": trade.analysis.bear_scenario if hasattr(trade, 'analysis') else "",
                            "status": trade.analysis.status if hasattr(trade, 'analysis') else None,
                            "completed_at": trade.analysis.completed_at if hasattr(trade, 'analysis') else None
                        } if hasattr(trade, 'analysis') else None,
                        "trade_history": [
                            {
                                "buy": str(history.buy),
                                "target": str(history.target),
                                "sl": str(history.sl),
                                "timestamp": history.timestamp.isoformat(),
                                "risk_reward_ratio": str(history.risk_reward_ratio),
                                "potential_profit_percentage": str(history.potential_profit_percentage),
                                "stop_loss_percentage": str(history.stop_loss_percentage)
                            }
                            for history in trade.history.all()
                        ],
                        "created_at": trade.created_at.isoformat(),
                        "updated_at": trade.updated_at.isoformat()
                    }
                    for trade in trades
                ]
            }
        })

    async def trade_update(self, event):
        """Handle trade update messages."""
        data = event["data"]
        
        # Check if user has access to this trade
        trade = await self.get_trade(data["trade_id"])
        if not trade or not trade.is_accessible_to_user(self.user):
            return

        # Create notification
        await self.create_notification(trade, data)

        # Send update to client
        await self.send_json({
            "type": "trade_update",
            "data": data
        })

    async def notification(self, event):
        """Handle notification messages."""
        await self.send_json({
            "type": "notification",
            "data": event["data"]
        })

    @database_sync_to_async
    def get_trade(self, trade_id):
        """Get trade by ID."""
        try:
            return Trade.objects.get(id=trade_id)
        except Trade.DoesNotExist:
            return None

    @database_sync_to_async
    def create_notification(self, trade, data):
        """Create a notification for the trade update."""
        message = f"Trade update for {trade.company.trading_symbol}: {data.get('action', 'updated')}"
        priority = "high" if data.get("trade_status") == Trade.Status.ACTIVE else "normal"
        
        return TradeNotification.create_trade_notification(
            user=self.user,
            trade=trade,
            notification_type=TradeNotification.NotificationType.TRADE_UPDATE,
            message=message,
            priority=priority
        ) 