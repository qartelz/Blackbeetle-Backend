from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging
from typing import Dict, List
from django.db import transaction
from datetime import timedelta
import traceback

from .models import Trade, TradeNotification, Company
from apps.subscriptions.models import Subscription, Plan

logger = logging.getLogger(__name__)

TRADE_MODEL = Trade


class PlanConfig:
    """Configuration for subscription plan access levels."""

    PLAN_LEVELS = {
        'BASIC': ['BASIC'],
        'PREMIUM': ['BASIC', 'PREMIUM'],
        'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM'],
        'FREE_TRIAL': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
    }

    TRADE_LIMITS = {
        'BASIC': 6,
        'PREMIUM': 9,
        'SUPER_PREMIUM': float('inf'),
        'FREE_TRIAL': float('inf')
    }

    @classmethod
    def get_accessible_plans(cls, plan_type: str) -> List[str]:
        return cls.PLAN_LEVELS.get(plan_type, [])

    @classmethod
    def get_trade_limit(cls, plan_type: str) -> int:
        return cls.TRADE_LIMITS.get(plan_type, 0)


class TradeUpdateManager:
    """Manages trade updates and broadcasting."""

    @classmethod
    def prepare_trade_data(cls, trade: Trade, action: str = "updated") -> Dict:
        try:
            # Determine message type based on trade status
            message_type = "trade_completed" if trade.status == 'COMPLETED' else "trade_update"
            
            data = {
                "trade_id": trade.id,
                "action": action,
                "message_type": message_type,
                "trade_status": trade.status,
                "plan_type": trade.plan_type,
                "update_type": "stock" if getattr(trade, 'is_stock_trade', False) else "index",
                "timestamp": timezone.now().isoformat(),
                "company": {
                    "id": trade.company.id,
                    "symbol": trade.company.trading_symbol,
                    "name": trade.company.script_name
                } if hasattr(trade, 'company') else None,
                "trade_type": trade.trade_type,
                "warzone": str(trade.warzone),
                "image": trade.image.url if trade.image else None
            }

            return data
        except Exception as e:
            return {
                "trade_id": getattr(trade, 'id', 'unknown'),
                "action": action,
                "error": str(e)
            }


class TradeSignalHandler:
    """Handles trade-related signals and broadcasts updates."""

    @staticmethod
    def get_user_active_trade_count(user, subscription):
        try:
            count = TRADE_MODEL.objects.filter(
                user=user,
                status__in=['ACTIVE'],
                created_at__gte=subscription.start_date
            ).count()
            return count
        except Exception:
            return 0

    @staticmethod
    def get_user_accessible_trades(user, subscription):
        """Get list of trades accessible to user based on subscription."""
        try:
            # Special handling for SUPER_PREMIUM and FREE_TRIAL users - get ALL trades
            if subscription.plan.name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
                all_trades = TRADE_MODEL.objects.filter(
                    status__in=['ACTIVE', 'COMPLETED']
                ).values_list('id', flat=True)
                return set(all_trades)
            
            # Standard logic for other plan types
            # Get trades created after subscription start
            new_trades = TRADE_MODEL.objects.filter(
                status__in=['ACTIVE', 'COMPLETED'],
                created_at__gte=subscription.start_date,
                plan_type__in=PlanConfig.get_accessible_plans(subscription.plan.name)
            )

            # Get previously active trades from before subscription
            previous_trades = TRADE_MODEL.objects.filter(
                status__in=['ACTIVE', 'COMPLETED'],
                created_at__lt=subscription.start_date,
                updated_at__gte=subscription.start_date
            )

            # Combine both querysets
            accessible_trades = new_trades.union(previous_trades)
            return set(accessible_trades.values_list('id', flat=True))
        except Exception:
            return set()

    @staticmethod
    def should_send_trade_update(user, trade, subscription):
        """
        Determine if a user should receive an update for a specific trade based on
        their subscription level and whether the trade is in their accessible list.
        """
        try:
            # Special case: SUPER_PREMIUM and FREE_TRIAL users always get all trade updates
            if subscription.plan.name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
                return True
            
            # Get list of trades this user has access to
            accessible_trades = TradeSignalHandler.get_user_accessible_trades(user, subscription)
            
            # Only send updates for trades the user has access to
            return trade.id in accessible_trades
        
        except Exception as e:
            logger.error(f"Error checking if user {user.id} should receive trade update: {str(e)}")
            return False

    @staticmethod
    def process_trade_update(trade: Trade, action: str = "updated"):
        """Unified method to handle trade updates - creates notification and sends WebSocket update"""
        try:
            # Get all active subscriptions
            subscriptions = Subscription.objects.filter(
                is_active=True,
                end_date__gt=timezone.now()
            ).select_related('user', 'plan')

            # Get channel layer for WebSocket communication
            channel_layer = get_channel_layer()
            
            # Prepare trade data once
            trade_data = TradeUpdateManager.prepare_trade_data(trade, action)
            
            # Process notification for each eligible user
            created_notifications = set()

            # Process users based on access rules
            for subscription in subscriptions:
                user = subscription.user
                
                # Check if user should receive this update using Trade model's helper
                if trade.is_trade_accessible(user, subscription):
                    # Create unique key for this notification
                    notification_key = f"{user.id}_{trade.id}_{trade.status}"
                    
                    # Create notification if not already created
                    if notification_key not in created_notifications:
                        # Create notification in database
                        message_type = "trade_completed" if trade.status == 'COMPLETED' else "trade_update"
                        message = f"Trade {'completed' if trade.status == 'COMPLETED' else 'updated'}: {trade.company.trading_symbol}"
                        
                        TradeNotification.create_trade_notification(
                            user=user,
                            trade=trade,
                            notification_type=TradeNotification.NotificationType.TRADE_COMPLETED if trade.status == 'COMPLETED' else TradeNotification.NotificationType.TRADE_UPDATE,
                            message=message
                        )
                        
                        created_notifications.add(notification_key)
                    
                    # Send WebSocket update
                    group_name = f"trade_updates_{user.id}"
                    
                    # Customize message for this user if needed
                    user_trade_data = trade_data.copy()
                    if trade.status == 'COMPLETED':
                        user_trade_data['message_type'] = 'trade_completed'
                        
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {
                            "type": "trade_update",
                            "data": user_trade_data
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Error processing trade update: {str(e)}")
            # Don't re-raise exception


@receiver(post_save, sender=Trade)
def handle_trade_update(sender, instance, created, **kwargs):
    """Handle trade updates and broadcast to relevant users."""
    try:
        action = "created" if created else "updated"
        
        # Process trade update if it's active or completed
        if instance.status in ['ACTIVE', 'COMPLETED']:
            # Use the unified method instead of calling broadcast and notification separately
            TradeSignalHandler.process_trade_update(instance, action)
            
    except Exception:
        pass
