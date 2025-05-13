from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging
from typing import Dict, List, Optional
from datetime import timedelta

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
    
    TRADE_LIMITS = {
        'BASIC': 6,
        'PREMIUM': 15,
        'SUPER_PREMIUM': float('inf')
    }
    
    @classmethod
    def get_accessible_plans(cls, plan_type: str) -> List[str]:
        """Get list of accessible plan types for a given plan."""
        return cls.PLAN_LEVELS.get(plan_type, [])
    
    @classmethod
    def get_trade_limit(cls, plan_type: str) -> int:
        """Get trade limit for a given plan type."""
        return cls.TRADE_LIMITS.get(plan_type, 0)


class TradeUpdateManager:
    """Manages trade updates and caching."""
    
    CACHE_TIMEOUT = 3600  # 1 hour
    CACHE_PREFIX = "trade_updates_"
    
    @classmethod
    def get_cache_key(cls, user_id: int, plan_type: str) -> str:
        """Generate cache key for user's trade updates."""
        return f"{cls.CACHE_PREFIX}{user_id}_{plan_type}"
    
    @classmethod
    def prepare_trade_data(cls, trade: Trade, action: str = "updated") -> Dict:
        """Prepare trade data for broadcasting."""
        return {
            "trade_id": trade.id,
            "action": action,
            "trade_status": trade.status,
            "plan_type": trade.plan_type,
            "update_type": "stock" if trade.is_stock_trade else "crypto",
            "timestamp": timezone.now().isoformat()
        }
    
    @classmethod
    def get_subscriber_groups(cls, trade: Trade) -> List[str]:
        """Get list of channel groups to broadcast to."""
        accessible_plans = PlanConfig.get_accessible_plans(trade.plan_type)
        return [f"trade_updates_{plan}" for plan in accessible_plans]


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
            accessible_plans = PlanConfig.get_accessible_plans(trade.plan_type)
            subscriptions = Subscription.objects.filter(
                plan__name__in=accessible_plans,
                is_active=True,
                end_date__gt=timezone.now()
            )
            
            for subscription in subscriptions:
                TradeNotification.create_trade_notification(
                    user=subscription.user,
                    trade=trade,
                    notification_type=TradeNotification.NotificationType.TRADE_UPDATE,
                    message=f"Trade update for {trade.company.trading_symbol}: {action}",
                    priority=TradeNotification.Priority.HIGH if trade.status == Trade.Status.ACTIVE else TradeNotification.Priority.NORMAL
                )
            
            logger.info(f"Created notifications for trade {trade.id} for {subscriptions.count()} users")
            
        except Exception as e:
            logger.error(f"Error creating trade notifications: {str(e)}")


@receiver(post_save, sender=Trade)
def handle_trade_update(sender, instance, created, **kwargs):
    """Handle trade updates and broadcast to relevant users."""
    try:
        action = "created" if created else "updated"
        TradeSignalHandler.broadcast_trade_update(instance, action)
        TradeSignalHandler.create_trade_notification(instance, action)
        
        # Clear relevant caches
        cache_key = TradeUpdateManager.get_cache_key(instance.user.id, instance.plan_type)
        cache.delete(cache_key)
        
    except Exception as e:
        logger.error(f"Error handling trade update signal: {str(e)}")
