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
        except Exception as e:
            logger.error(f"Error getting active trade count: {str(e)}")
            return 0

    @staticmethod
    def get_user_accessible_trades(user, subscription):
        """Get list of trades accessible to user based on subscription."""
        try:
            # Special handling for SUPER_PREMIUM and FREE_TRIAL users
            if subscription.plan.name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
                all_trades = TRADE_MODEL.objects.filter(
                    status__in=['ACTIVE', 'COMPLETED']
                )
                accessible_trades = [t.id for t in all_trades if t.is_trade_accessible(user, subscription)]
                return set(accessible_trades)
            
            # Get allowed plan types based on subscription
            plan_filters = {
                'BASIC': ['BASIC'],
                'PREMIUM': ['BASIC', 'PREMIUM'],
            }
            allowed_plans = plan_filters.get(subscription.plan.name, [])
            
            # Get trades created after subscription start (new trades)
            new_trades_limit = 9 if subscription.plan.name == 'PREMIUM' else 6
            new_trades = TRADE_MODEL.objects.filter(
                status__in=['ACTIVE', 'COMPLETED'],
                created_at__gte=subscription.start_date,
                plan_type__in=allowed_plans
            ).order_by('created_at')[:new_trades_limit].values_list('id', flat=True)
            
            # Get previously active trades from before subscription (up to 6)
            previous_trades = TRADE_MODEL.objects.filter(
                status__in=['ACTIVE', 'COMPLETED'],
                created_at__lt=subscription.start_date,
                plan_type__in=allowed_plans
            ).order_by('-created_at')[:6].values_list('id', flat=True)
            
            # Combine both sets of trades
            accessible_trades = set(new_trades) | set(previous_trades)
            
            # Add free trades
            free_trades = TRADE_MODEL.objects.filter(
                is_free_call=True,
                status__in=['ACTIVE', 'COMPLETED']
            ).values_list('id', flat=True)
            
            return accessible_trades | set(free_trades)
            
        except Exception as e:
            logger.error(f"Error getting accessible trades: {str(e)}")
            logger.error(traceback.format_exc())
            return set()

    @staticmethod
    def should_send_trade_update(user, trade, subscription):
        """Determine if a user should receive an update for a specific trade."""
        try:
            # First check if trade is free - all users get free trade notifications
            if trade.is_free_call:
                return True

            # Check subscription validity
            if not subscription or not subscription.is_active:
                return False

            # Get plan name and subscription dates
            plan_name = subscription.plan.name
            subscription_start = subscription.start_date

            # SUPER_PREMIUM and FREE_TRIAL get all notifications
            if plan_name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
                return True

            # For other plans, check if trade is in their allowed plan types
            allowed_plans = {
                'BASIC': ['BASIC'],
                'PREMIUM': ['BASIC', 'PREMIUM'],
            }.get(plan_name, [])

            if trade.plan_type not in allowed_plans:
                return False

            # Check if this is a new trade (after subscription)
            if trade.created_at >= subscription_start:
                # Get count of new trades
                new_trades = TRADE_MODEL.objects.filter(
                    status__in=['ACTIVE', 'COMPLETED'],
                    created_at__gte=subscription_start,
                    plan_type__in=allowed_plans
                ).order_by('created_at')
                
                # Apply limits based on plan
                limit = 9 if plan_name == 'PREMIUM' else 6
                allowed_trades = list(new_trades[:limit])
                return trade.id in [t.id for t in allowed_trades]
            else:
                # For previous trades, all plans get up to 6
                previous_trades = TRADE_MODEL.objects.filter(
                    status__in=['ACTIVE', 'COMPLETED'],
                    created_at__lt=subscription_start,
                    plan_type__in=allowed_plans
                ).order_by('-created_at')[:6]
                return trade.id in [t.id for t in previous_trades]

        except Exception as e:
            logger.error(f"Error checking notification eligibility: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    def process_trade_update(trade: Trade, action: str = "updated"):
        """Process trade updates and send notifications."""
        try:
            # Skip notifications for PENDING trades
            if trade.status == 'PENDING':
                logger.info(f"Skipping notification for PENDING trade {trade.id}")
                return
            
            # Get all active subscriptions
            subscriptions = Subscription.objects.filter(
                is_active=True,
                end_date__gt=timezone.now()
            ).select_related('user', 'plan')

            # Get channel layer for WebSocket communication
            channel_layer = get_channel_layer()
            
            # Prepare trade data once
            trade_data = TradeUpdateManager.prepare_trade_data(trade, action)
            
            # Track processed notifications to avoid duplicates
            processed_users = set()

            # Process each subscription
            for subscription in subscriptions:
                user = subscription.user
                
                # Skip if we've already processed this user
                if user.id in processed_users:
                    continue
                
                # Check if user should receive this notification
                if TradeSignalHandler.should_send_trade_update(user, trade, subscription):
                    try:
                        # Create notification
                        notification_type = (
                            TradeNotification.NotificationType.TRADE_COMPLETED 
                            if trade.status == 'COMPLETED' 
                            else TradeNotification.NotificationType.TRADE_UPDATE
                        )
                        
                        message = (
                            f"Trade completed: {trade.company.trading_symbol}"
                            if trade.status == 'COMPLETED'
                            else f"Trade update: {trade.company.trading_symbol}"
                        )
                        
                        # Create the notification with error handling
                        with transaction.atomic():
                            notification = TradeNotification.create_trade_notification(
                                user=user,
                                trade=trade,
                                notification_type=notification_type,
                                message=message,
                                priority=TradeNotification.Priority.HIGH if trade.status == 'ACTIVE' else TradeNotification.Priority.NORMAL
                            )
                            
                            if notification:
                                # Send WebSocket update
                                group_name = f"trade_updates_{user.id}"
                                
                                # Customize message for this user
                                user_trade_data = trade_data.copy()
                                user_trade_data['notification_id'] = notification.id
                                
                                async_to_sync(channel_layer.group_send)(
                                    group_name,
                                    {
                                        "type": "trade_update",
                                        "data": user_trade_data
                                    }
                                )
                                
                                # Also send to notification channel
                                notification_group = f"notification_updates_{user.id}"
                                async_to_sync(channel_layer.group_send)(
                                    notification_group,
                                    {
                                        "type": "notification_message",
                                        "message": {
                                            "id": notification.id,
                                            "type": notification_type,
                                            "message": message,
                                            "created_at": notification.created_at.isoformat(),
                                            "trade_id": trade.id,
                                            "is_read": False
                                        }
                                    }
                                )
                                
                                logger.info(f"Successfully sent notification to user {user.id} for trade {trade.id}")
                        
                        processed_users.add(user.id)
                        
                    except Exception as e:
                        logger.error(f"Error processing notification for user {user.id}: {str(e)}")
                        logger.error(traceback.format_exc())
                        continue
                        
        except Exception as e:
            logger.error(f"Error in process_trade_update: {str(e)}")
            logger.error(traceback.format_exc())


@receiver(post_save, sender=Trade)
def handle_trade_update(sender, instance, created, **kwargs):
    """Handle trade updates and broadcast to relevant users."""
    try:
        # Skip if the trade is being created and is in PENDING status
        if created and instance.status == 'PENDING':
            return
            
        action = "created" if created else "updated"
        
        # Process trade update if it's active or completed
        if instance.status in ['ACTIVE', 'COMPLETED']:
            # Queue the notification processing in a transaction
            transaction.on_commit(
                lambda: TradeSignalHandler.process_trade_update(instance, action)
            )
            
    except Exception as e:
        logger.error(f"Error in handle_trade_update signal: {str(e)}")
        logger.error(traceback.format_exc())
