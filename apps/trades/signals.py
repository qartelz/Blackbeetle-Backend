from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging
from typing import Dict, List

from .models import Trade, TradeNotification
from apps.subscriptions.models import Subscription

logger = logging.getLogger(__name__)

class PlanConfig:
    """Configuration for subscription plan access levels."""
    
    PLAN_LEVELS = {
        'BASIC': ['BASIC'],
        'PREMIUM': ['BASIC', 'PREMIUM'],
        'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
    }
    
    @classmethod
    def get_accessible_plans(cls, plan_type: str) -> List[str]:
        """Get list of accessible plan types for a given plan."""
        return cls.PLAN_LEVELS.get(plan_type, [])


class TradeUpdateManager:
    """Manages trade updates and broadcasting."""
    
    @classmethod
    def prepare_trade_data(cls, trade: Trade, action: str = "updated") -> Dict:
        """Prepare trade data for broadcasting."""
        return {
            "trade_id": trade.id,
            "action": action,
            "trade_status": trade.status,
            "plan_type": trade.plan_type,
            "update_type": "stock" if trade.is_stock_trade else "index",
            "timestamp": timezone.now().isoformat(),
            "company": {
                "id": trade.company.id,
                "symbol": trade.company.trading_symbol,
                "name": trade.company.script_name
            },
            "trade_type": trade.trade_type,
            "warzone": str(trade.warzone),
            "image": trade.image.url if trade.image else None
        }
    
    @classmethod
    def get_subscriber_groups(cls, trade: Trade) -> List[str]:
        """Get list of channel groups to broadcast to."""
        # Get all active subscriptions that can access this trade
        subscriptions = Subscription.objects.filter(
            is_active=True,
            end_date__gt=timezone.now(),
            plan__name__in=PlanConfig.get_accessible_plans(trade.plan_type)
        )
        
        # Create group names for each user
        return [f"trade_updates_{sub.user.id}" for sub in subscriptions]


class TradeSignalHandler:
    """Handles trade-related signals and broadcasts updates."""
    
    @staticmethod
    def broadcast_trade_update(trade: Trade, action: str = "updated"):
        """Broadcast trade update to relevant subscribers."""
        try:
            channel_layer = get_channel_layer()
            trade_data = TradeUpdateManager.prepare_trade_data(trade, action)
            groups = TradeUpdateManager.get_subscriber_groups(trade)
            
            for group in groups:
                async_to_sync(channel_layer.group_send)(
                    group,
                    {
                        "type": "trade_update",
                        "data": trade_data
                    }
                )
            
            logger.info(f"Broadcast trade update for {trade.id} to {len(groups)} groups")
            
        except Exception as e:
            logger.error(f"Error broadcasting trade update: {str(e)}")
    
    @staticmethod
    def create_trade_notification(trade: Trade, action: str = "updated"):
        """Create notifications for relevant users."""
        try:
            # Get all active subscriptions that can access this trade
            subscriptions = Subscription.objects.filter(
                is_active=True,
                end_date__gt=timezone.now(),
                plan__name__in=PlanConfig.get_accessible_plans(trade.plan_type)
            )
            
            for subscription in subscriptions:
                try:
                    TradeNotification.create_trade_notification(
                        user=subscription.user,
                        trade=trade,
                        notification_type=TradeNotification.NotificationType.TRADE_UPDATE,
                        message=f"Trade update for {trade.company.trading_symbol}: {action}",
                        priority=TradeNotification.Priority.HIGH if trade.status == Trade.Status.ACTIVE else TradeNotification.Priority.NORMAL
                    )
                except Exception as e:
                    logger.error(f"Error creating notification for user {subscription.user.id}: {str(e)}")
                    continue
            
            logger.info(f"Created notifications for trade {trade.id} for {subscriptions.count()} users")
            
        except Exception as e:
            logger.error(f"Error creating trade notifications: {str(e)}")


@receiver(post_save, sender=Trade)
def handle_trade_update(sender, instance, created, **kwargs):
    """Handle trade updates and broadcast to relevant users."""
    try:
        action = "created" if created else "updated"
        
        # Broadcast the update
        TradeSignalHandler.broadcast_trade_update(instance, action)
        
        # Create notifications
        TradeSignalHandler.create_trade_notification(instance, action)
        
        logger.info(f"Successfully handled trade update for trade {instance.id}")
        
    except Exception as e:
        logger.error(f"Error handling trade update signal: {str(e)}")
