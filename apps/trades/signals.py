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
            # Special handling for SUPER_PREMIUM and FREE_TRIAL users - get ALL trades
            if subscription.plan.name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
                all_trades = TRADE_MODEL.objects.filter(
                    status__in=['ACTIVE', 'COMPLETED']
                ).values_list('id', flat=True)
                return set(all_trades)
            
            # Get allowed plan types based on subscription
            plan_filters = {
                'BASIC': ['BASIC'],
<<<<<<< Updated upstream
                'PREMIUM': ['BASIC', 'PREMIUM'],  # Premium users can access both Basic and Premium trades
=======
                'PREMIUM': ['BASIC', 'PREMIUM'],  # Make sure PREMIUM users can access both BASIC and PREMIUM trades
>>>>>>> Stashed changes
            }
            allowed_plans = plan_filters.get(subscription.plan.name, [])
            
            # Get trades created after subscription start (new trades)
            new_trades_limit = 9 if subscription.plan.name == 'PREMIUM' else 6
            new_trades = TRADE_MODEL.objects.filter(
                status__in=['ACTIVE', 'COMPLETED'],
                created_at__gte=subscription.start_date,
                plan_type__in=allowed_plans
            ).order_by('created_at')[:new_trades_limit].values_list('id', flat=True)
            
            # Get previously active trades from before subscription (always up to 6)
            previous_trades = TRADE_MODEL.objects.filter(
                status__in=['ACTIVE', 'COMPLETED'],
                created_at__lt=subscription.start_date,
                plan_type__in=allowed_plans
            ).order_by('-created_at')[:6].values_list('id', flat=True)
            
            # Combine both sets of trades
            accessible_trades = set(list(new_trades) + list(previous_trades))
            
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
        """Determine if a user should receive updates for a trade."""
        try:
            # Free trades are accessible to everyone
            if trade.is_free_call:
                return True
                
            # No subscription - only free trades
            if not subscription or not subscription.is_active:
                return False
                
            # SUPER_PREMIUM and FREE_TRIAL get all trades
            if subscription.plan.name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
                return True
                
            # For other plans, check trade accessibility
            return trade.is_trade_accessible(user, subscription)
            
        except Exception as e:
            logger.error(f"Error checking trade update eligibility: {str(e)}")
            return False

    @staticmethod
    def process_trade_update(trade: Trade, action: str = "updated"):
        """Unified method to handle trade updates - creates notification and sends WebSocket update"""
        try:
            # Skip notifications for PENDING trades
            if trade.status == 'PENDING':
                return
            
            # Get all active subscriptions
            subscriptions = Subscription.objects.filter(
                is_active=True,
                end_date__gt=timezone.now()
            ).select_related('user', 'plan')

            # Get channel layer for WebSocket communication
            channel_layer = get_channel_layer()
            
            # Create notifications for each eligible user
            notification_count = 0
            
            for subscription in subscriptions:
                user = subscription.user
                
<<<<<<< Updated upstream
                # Check if user should receive this update
                if TradeSignalHandler.should_send_trade_update(user, trade, subscription):
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
            logger.error(traceback.format_exc())
=======
                # Check if user should receive this trade update
                if not TradeSignalHandler.should_send_trade_update(user, trade, subscription):
                    continue
                    
                # Create notification
                notification = Notification.objects.create(
                    user=user,
                    type='TRADE',
                    message_type='trade_update',
                    short_message=f"Trade updated: {trade.company.tradingSymbol}",
                    detailed_message=f"The trade for {trade.company.tradingSymbol} has been updated",
                    related_url=f"/trades/{trade.id}",
                    trade_status=trade.status,
                    trade_id=trade.id,
                    is_redirectable=True,
                    data={
                        'updated_company': trade.company.to_dict(),
                        'subscription': subscription.to_dict()
                    }
                )
                notification_count += 1
                
                # Send WebSocket notification
                async_to_sync(channel_layer.group_send)(
                    f"notification_updates_{user.id}",
                    {
                        'type': 'notification',
                        'data': notification.to_dict()
                    }
                )
                
            logger.info(f"Created {notification_count} notifications for trade {trade.id}")
            
        except Exception as e:
            logger.error(f"Error processing trade update: {str(e)}")
            raise
>>>>>>> Stashed changes


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
