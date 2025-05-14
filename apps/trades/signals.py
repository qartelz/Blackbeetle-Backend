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

# Import all required models at module level
from .models import Trade, TradeNotification, Company
from apps.subscriptions.models import Subscription, Plan

logger = logging.getLogger(__name__)

# Global Trade model reference
TRADE_MODEL = Trade

class PlanConfig:
    """Configuration for subscription plan access levels."""
    
    PLAN_LEVELS = {
        'BASIC': ['BASIC'],
        'PREMIUM': ['BASIC', 'PREMIUM'],
        'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM'],
        'FREE_TRIAL': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
    }
    
<<<<<<< HEAD
=======
    TRADE_LIMITS = {
        'BASIC': 6,
        'PREMIUM': 9,
        'SUPER_PREMIUM': float('inf'),
        'FREE_TRIAL': float('inf')
    }
    
>>>>>>> e5d635f (best possble output updated)
    @classmethod
    def get_accessible_plans(cls, plan_type: str) -> List[str]:
        """Get list of accessible plan types for a given plan."""
        return cls.PLAN_LEVELS.get(plan_type, [])


class TradeUpdateManager:
    """Manages trade updates and broadcasting."""
    
    @classmethod
    def prepare_trade_data(cls, trade: Trade, action: str = "updated") -> Dict:
        """Prepare trade data for broadcasting."""
<<<<<<< HEAD
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
        try:
            with transaction.atomic():
                # Get all active subscriptions that can access this trade
                subscriptions = Subscription.objects.filter(
                    is_active=True,
                    end_date__gt=timezone.now(),
                    plan__name__in=PlanConfig.get_accessible_plans(trade.plan_type)
                ).select_related('plan')

                # Create group names for each user
                groups = []
                for sub in subscriptions:
                    if sub.plan.name == 'BASIC':
                        # Count new trades after subscription
                        new_trades_count = Trade.objects.filter(
                            created_at__gte=sub.start_date,
                            created_at__lte=timezone.now()
                        ).count()
                        
                        # Only add to groups if within new trade limit (6)
                        if new_trades_count <= 6:
                            groups.append(f"trade_updates_{sub.user.id}")
                    elif sub.plan.name == 'PREMIUM':
                        # Count new trades after subscription
                        new_trades_count = Trade.objects.filter(
                            created_at__gte=sub.start_date,
                            created_at__lte=timezone.now()
                        ).count()
                        
                        # Only add to groups if within new trade limit (9)
                        if new_trades_count <= 9:
                            groups.append(f"trade_updates_{sub.user.id}")
                    else:  # SUPER_PREMIUM or FREE_TRIAL
                        # No limits for these plans
                        groups.append(f"trade_updates_{sub.user.id}")

                return groups
        except Exception as e:
            logger.error(f"Error getting subscriber groups: {str(e)}")
            return []
=======
        try:
            logger.info(f"Preparing trade data for trade ID: {trade.id}")
            logger.info(f"Trade object type: {type(trade)}")
            logger.info(f"Trade attributes: {dir(trade)}")
            
            data = {
                "trade_id": trade.id,
                "action": action,
                "trade_status": trade.status,
                "plan_type": trade.plan_type,
                "update_type": "stock" if hasattr(trade, 'is_stock_trade') and trade.is_stock_trade else "crypto",
                "timestamp": timezone.now().isoformat(),
            }
            
            if hasattr(trade, 'company'):
                data["company"] = {
                    "id": trade.company.id,
                    "symbol": trade.company.trading_symbol,
                    "name": trade.company.script_name
                }
                logger.info(f"Added company data for trade {trade.id}")
            
            logger.info(f"Successfully prepared trade data: {data}")
            return data
            
        except Exception as e:
            logger.error(f"Error preparing trade data: {str(e)}")
            logger.error(f"Error traceback: {traceback.format_exc()}")
            return {
                "trade_id": trade.id if hasattr(trade, 'id') else 'unknown',
                "action": action,
                "error": str(e)
            }
>>>>>>> e5d635f (best possble output updated)


class TradeSignalHandler:
    """Handles trade-related signals and broadcasts updates."""

    @staticmethod
    def get_user_active_trade_count(user, subscription):
        """Get count of active trades for a user after subscription start."""
        try:
            logger.info(f"Getting active trade count for user {user.id}")
            # Use the global Trade model reference
            count = TRADE_MODEL.objects.filter(
                user=user,
                status__in=['ACTIVE'],
                created_at__gte=subscription.start_date
            ).count()
            logger.info(f"Found {count} active trades for user {user.id}")
            return count
        except Exception as e:
            logger.error(f"Error getting active trade count: {str(e)}")
            logger.error(f"Error traceback: {traceback.format_exc()}")
            return 0

    @staticmethod
    def should_send_trade_update(user, trade, subscription):
        """Determine if trade update should be sent to user based on their subscription."""
        try:
            logger.info(f"Checking if should send trade update for user {user.id}, trade {trade.id}")
            
            # If trade was created before subscription, always send
            if trade.created_at < subscription.start_date:
                logger.info(f"Trade {trade.id} was created before subscription, sending update")
                return True

            # For SUPER_PREMIUM and FREE_TRIAL, send all trades
            if subscription.plan.name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
                logger.info(f"User {user.id} has {subscription.plan.name} plan, sending all trades")
                return True

            # For BASIC and PREMIUM, check trade limits
            active_count = TradeSignalHandler.get_user_active_trade_count(user, subscription)
            plan_limit = PlanConfig.get_trade_limit(subscription.plan.name)
            
            should_send = active_count < plan_limit
            logger.info(f"User {user.id} has {active_count}/{plan_limit} trades, should send: {should_send}")
            return should_send

        except Exception as e:
            logger.error(f"Error checking trade update eligibility: {str(e)}")
            logger.error(f"Error traceback: {traceback.format_exc()}")
            return False

    @staticmethod
    def broadcast_trade_update(trade: Trade, action: str = "updated"):
        """Broadcast trade update to relevant subscribers."""
        try:
            logger.info(f"Broadcasting trade update for trade {trade.id}")
            channel_layer = get_channel_layer()
            trade_data = TradeUpdateManager.prepare_trade_data(trade, action)
            
<<<<<<< HEAD
            if not groups:
                logger.info(f"No eligible subscribers for trade {trade.id}")
                return

            for group in groups:
                async_to_sync(channel_layer.group_send)(
                    group,
                    {
                        "type": "trade_update",
                        "data": trade_data
                    }
                )
=======
            # Get all active subscriptions
            subscriptions = Subscription.objects.filter(
                is_active=True,
                end_date__gt=timezone.now()
            ).select_related('user', 'plan')
>>>>>>> e5d635f (best possble output updated)
            
            logger.info(f"Found {subscriptions.count()} active subscriptions")

            for subscription in subscriptions:
                # Check if user should receive this trade update
                if TradeSignalHandler.should_send_trade_update(subscription.user, trade, subscription):
                    group_name = f"trade_updates_{subscription.user.id}"
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {
                            "type": "trade_update",
                            "data": trade_data
                        }
                    )
                    logger.info(f"Broadcast trade update for {trade.id} to user {subscription.user.id}")
            
        except Exception as e:
            logger.error(f"Error broadcasting trade update: {str(e)}")
            logger.error(f"Error traceback: {traceback.format_exc()}")
    
    @staticmethod
    def create_trade_notification(trade: Trade, action: str = "updated"):
        """Create notifications for relevant users."""
        try:
<<<<<<< HEAD
            with transaction.atomic():
                # Get all active subscriptions that can access this trade
                subscriptions = Subscription.objects.filter(
                    is_active=True,
                    end_date__gt=timezone.now(),
                    plan__name__in=PlanConfig.get_accessible_plans(trade.plan_type)
                ).select_related('plan')
                
                for subscription in subscriptions:
                    try:
                        if subscription.plan.name == 'BASIC':
                            # Count new trades after subscription
                            new_trades_count = Trade.objects.filter(
                                created_at__gte=subscription.start_date,
                                created_at__lte=timezone.now()
                            ).count()
                            
                            # Only create notification if within new trade limit (6)
                            if new_trades_count <= 6:
                                TradeNotification.create_trade_notification(
                                    user=subscription.user,
                                    trade=trade,
                                    notification_type=TradeNotification.NotificationType.TRADE_UPDATE,
                                    message=f"Trade update for {trade.company.trading_symbol}: {action}",
                                    priority=TradeNotification.Priority.HIGH if trade.status == Trade.Status.ACTIVE else TradeNotification.Priority.NORMAL
                                )
                        elif subscription.plan.name == 'PREMIUM':
                            # Count new trades after subscription
                            new_trades_count = Trade.objects.filter(
                                created_at__gte=subscription.start_date,
                                created_at__lte=timezone.now()
                            ).count()
                            
                            # Only create notification if within new trade limit (9)
                            if new_trades_count <= 9:
                                TradeNotification.create_trade_notification(
                                    user=subscription.user,
                                    trade=trade,
                                    notification_type=TradeNotification.NotificationType.TRADE_UPDATE,
                                    message=f"Trade update for {trade.company.trading_symbol}: {action}",
                                    priority=TradeNotification.Priority.HIGH if trade.status == Trade.Status.ACTIVE else TradeNotification.Priority.NORMAL
                                )
                        else:  # SUPER_PREMIUM or FREE_TRIAL
                            # No limits for these plans
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
                
                logger.info(f"Created notifications for trade {trade.id}")
=======
            logger.info(f"Creating trade notification for trade {trade.id}")
            # Get all active subscriptions
            subscriptions = Subscription.objects.filter(
                is_active=True,
                end_date__gt=timezone.now()
            ).select_related('user', 'plan')
            
            logger.info(f"Found {subscriptions.count()} active subscriptions for notifications")
            
            for subscription in subscriptions:
                # Check if user should receive this trade notification
                if TradeSignalHandler.should_send_trade_update(subscription.user, trade, subscription):
                    TradeNotification.create_trade_notification(
                        user=subscription.user,
                        trade=trade,
                        notification_type=TradeNotification.NotificationType.TRADE_UPDATE,
                        message=f"Trade update for {trade.company.trading_symbol}: {action}",
                        priority=TradeNotification.Priority.HIGH if trade.status == 'ACTIVE' else TradeNotification.Priority.NORMAL
                    )
                    logger.info(f"Created notification for trade {trade.id} for user {subscription.user.id}")
            
>>>>>>> e5d635f (best possble output updated)
        except Exception as e:
            logger.error(f"Error creating trade notifications: {str(e)}")
            logger.error(f"Error traceback: {traceback.format_exc()}")


@receiver(post_save, sender=Trade)
def handle_trade_update(sender, instance, created, **kwargs):
    """Handle trade updates and broadcast to relevant users."""
    try:
<<<<<<< HEAD
        action = "created" if created else "updated"
        
        # Broadcast the update
        TradeSignalHandler.broadcast_trade_update(instance, action)
        
        # Create notifications
        TradeSignalHandler.create_trade_notification(instance, action)
        
        logger.info(f"Successfully handled trade update for trade {instance.id}")
=======
        logger.info(f"Trade update signal received for trade {instance.id}")
        logger.info(f"Trade object type: {type(instance)}")
        logger.info(f"Trade attributes: {dir(instance)}")
        
        # Process if the trade is ACTIVE
        if instance.status == 'ACTIVE':
            action = "created" if created else "updated"
            logger.info(f"Processing ACTIVE trade update. Action type: {action}")
            
            TradeSignalHandler.broadcast_trade_update(instance, action)
            TradeSignalHandler.create_trade_notification(instance, action)
            
            # Clear relevant caches
            cache_key = TradeUpdateManager.get_cache_key(instance.user.id, instance.plan_type)
            cache.delete(cache_key)
            logger.info(f"Cleared cache for key: {cache_key}")
        else:
            logger.info(f"Skipping trade update for non-ACTIVE status: {instance.status}")
>>>>>>> e5d635f (best possble output updated)
        
    except Exception as e:
        logger.error(f"Error handling trade update signal: {str(e)}")
        logger.error(f"Error traceback: {traceback.format_exc()}")
