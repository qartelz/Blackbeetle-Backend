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

            logger.info(f"Prepared trade data: {data}")
            return data
        except Exception as e:
            logger.error(f"Error preparing trade data: {str(e)}")
            logger.error(traceback.format_exc())
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
        except Exception as e:
            logger.error(f"Error getting active trade count: {str(e)}")
            logger.error(traceback.format_exc())
            return 0

    @staticmethod
    def get_user_accessible_trades(user, subscription):
        """Get list of trades accessible to user based on subscription."""
        try:
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
                status_changed_at__gte=subscription.start_date
            )

            # Combine both querysets
            accessible_trades = new_trades.union(previous_trades)
            return set(accessible_trades.values_list('id', flat=True))
        except Exception as e:
            logger.error(f"Error getting accessible trades: {str(e)}")
            logger.error(traceback.format_exc())
            return set()

    @staticmethod
    def should_send_trade_update(user, trade, subscription):
        try:
            # If trade is not completed, use existing logic
            if trade.status != 'COMPLETED':
                if trade.created_at < subscription.start_date:
                    return True

                if subscription.plan.name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
                    return True

                active_count = TradeSignalHandler.get_user_active_trade_count(user, subscription)
                plan_limit = PlanConfig.get_trade_limit(subscription.plan.name)
                return active_count < plan_limit

            # For completed trades, check if user had access to this trade
            accessible_trades = TradeSignalHandler.get_user_accessible_trades(user, subscription)
            return trade.id in accessible_trades

        except Exception as e:
            logger.error(f"Error checking trade update eligibility: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    def broadcast_trade_update(trade: Trade, action: str = "updated"):
        try:
            channel_layer = get_channel_layer()
            trade_data = TradeUpdateManager.prepare_trade_data(trade, action)

            # Get all active subscriptions
            subscriptions = Subscription.objects.filter(
                is_active=True,
                end_date__gt=timezone.now()
            ).select_related('user', 'plan')

            for subscription in subscriptions:
                # Check if user should receive this update
                if TradeSignalHandler.should_send_trade_update(subscription.user, trade, subscription):
                    group_name = f"trade_updates_{subscription.user.id}"
                    
                    # Add subscription-specific data
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
                    logger.info(f"Sent {trade.status} trade update to user {subscription.user.id} for trade {trade.id}")
                else:
                    logger.info(f"Skipped sending trade {trade.id} update to user {subscription.user.id} - not accessible")

        except Exception as e:
            logger.error(f"Error broadcasting trade update: {str(e)}")
            logger.error(traceback.format_exc())

    @staticmethod
    def create_trade_notification(trade: Trade, action: str = "updated"):
        try:
            # Get all active subscriptions
            subscriptions = Subscription.objects.filter(
                is_active=True,
                end_date__gt=timezone.now()
            ).select_related('user', 'plan')

            # Track created notifications to prevent duplicates
            created_notifications = set()

            for subscription in subscriptions:
                if TradeSignalHandler.should_send_trade_update(subscription.user, trade, subscription):
                    # Create a unique key for this notification
                    notification_key = f"{subscription.user.id}_{trade.id}_{trade.status}"
                    
                    # Only create if not already created
                    if notification_key not in created_notifications:
                        message_type = "trade_completed" if trade.status == 'COMPLETED' else "trade_update"
                        message = f"Trade {'completed' if trade.status == 'COMPLETED' else 'updated'}: {trade.company.trading_symbol}"
                        
                        TradeNotification.create_trade_notification(
                            user=subscription.user,
                            trade=trade,
                            notification_type=TradeNotification.NotificationType.TRADE_COMPLETED if trade.status == 'COMPLETED' else TradeNotification.NotificationType.TRADE_UPDATE,
                            message=message
                        )
                        
                        created_notifications.add(notification_key)
                        
                        # Send WebSocket update
                        group_name = f"trade_updates_{subscription.user.id}"
                        channel_layer = get_channel_layer()
                        
                        user_trade_data = TradeUpdateManager.prepare_trade_data(trade, action).copy()
                        if trade.status == 'COMPLETED':
                            user_trade_data['message_type'] = 'trade_completed'
                            
                        async_to_sync(channel_layer.group_send)(
                            group_name,
                            {
                                "type": "trade_update",
                                "data": user_trade_data
                            }
                        )
                        
                        logger.info(f"Sent {trade.status} trade update to user {subscription.user.id} for trade {trade.id}")

        except Exception as e:
            logger.error(f"Error creating trade notification: {str(e)}")
            logger.error(traceback.format_exc())


@receiver(post_save, sender=Trade)
def handle_trade_update(sender, instance, created, **kwargs):
    """Handle trade updates and broadcast to relevant users."""
    try:
        action = "created" if created else "updated"
        
        # Handle both ACTIVE and COMPLETED trades
        if instance.status in ['ACTIVE', 'COMPLETED']:
            TradeSignalHandler.broadcast_trade_update(instance, action)
            TradeSignalHandler.create_trade_notification(instance, action)
            
            logger.info(f"Processed trade {instance.id} update - Status: {instance.status}, Action: {action}")
    except Exception as e:
        logger.error(f"Error handling trade update signal: {str(e)}")
        logger.error(traceback.format_exc())
