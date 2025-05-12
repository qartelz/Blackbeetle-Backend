from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync, sync_to_async
from .models import Trade
from apps.indexAndCommodity.models import Trade as IndexAndCommodityTrade
from .serializers.tradeconsumer_serializers import CompanySerializer, IndexAndCommoditySeraializer
from apps.subscriptions.models import Subscription
import logging
from django.utils import timezone
from functools import lru_cache
from typing import Dict, List, Any
from dataclasses import dataclass
import asyncio

logger = logging.getLogger(__name__)

@dataclass
class PlanConfig:
    """Represents configuration for subscription plan access levels."""
    levels: List[str]  # List of plan types that can access this trade


class TradeUpdateManager:
    """Utility class for managing trade update logic and configurations."""

    @staticmethod
    @lru_cache(maxsize=3)
    def get_plan_configs(plan_type: str) -> PlanConfig:
        """Retrieve cached plan configuration for a given plan type."""
        configs = {
            'BASIC': PlanConfig(['BASIC', 'PREMIUM', 'SUPER_PREMIUM']),
            'PREMIUM': PlanConfig(['PREMIUM', 'SUPER_PREMIUM']),
            'SUPER_PREMIUM': PlanConfig(['SUPER_PREMIUM'])
        }
        return configs.get(plan_type, PlanConfig([]))

    @staticmethod
    async def prepare_trade_data(
        instance: Any,
        serializer_class: Any,
        update_type: str,
        created: bool
    ) -> Dict[str, Any]:
        """Prepare the trade update data payload for broadcasting."""
        parent_object = instance.company if update_type == "stock" else instance.index_and_commodity
        action = (
            "created" if created and instance.status == "ACTIVE"
            else "cancelled" if instance.status in ["CANCELLED", "DELETED", "PENDING", "COMPLETED"]
            else "updated"
        )
        previous_status = instance.tracker.previous('status') if not created else None

        # Wrap serializer.data in sync_to_async since it's a sync operation
        serializer_data = await sync_to_async(lambda: serializer_class(parent_object).data)()

        return {
            "update_type": update_type,
            "action": action,
            "data": serializer_data,
            "plan_type": instance.plan_type,
            "trade_status": instance.status,
            "trade_id": instance.id,
            "is_realtime": True,
            "previous_status": previous_status,
        }


class TradeSignalHandler:
    """Handles broadcasting trade updates to subscribed users via WebSocket groups."""

    _pending_updates = {}  # For debouncing

    @staticmethod
    @lru_cache(maxsize=128)
    def _get_subscriber_groups_cached(plan_levels: tuple, timestamp: int) -> List[str]:
        """Fetch cached group names for subscribers with access to the given plan levels."""
        now = timezone.now()
        trade_time = timezone.datetime.fromtimestamp(timestamp, tz=timezone.utc)

        subscriptions = Subscription.objects.filter(
            plan__name__in=plan_levels,
            is_active=True,
            start_date__lte=now,
            end_date__gte=now,
            start_date__lte=trade_time
        ).select_related('user').prefetch_related('user__notification_preferences')

        # Filter users based on notification preferences
        valid_subscriptions = []
        for sub in subscriptions:
            user = sub.user
            if hasattr(user, 'notification_preferences'):
                prefs = user.notification_preferences
                if prefs.enable_trade_updates and prefs.enable_realtime_updates:
                    valid_subscriptions.append(sub)

        return [f"trade_updates_{sub.user.id}" for sub in valid_subscriptions]

    @staticmethod
    async def _get_subscriber_groups(plan_levels: List[str], trade_time) -> List[str]:
        """Get subscriber groups with 5-minute caching, async-compatible."""
        return await sync_to_async(TradeSignalHandler._get_subscriber_groups_cached)(
            tuple(plan_levels), int(trade_time.timestamp())
        )

    @staticmethod
    async def debounce_send(instance, update_type, serializer_class):
        """Debounce trade updates to batch within 100ms."""
        key = f"{update_type}_{instance.id}"
        if key not in TradeSignalHandler._pending_updates:
            TradeSignalHandler._pending_updates[key] = instance
            await asyncio.sleep(0.1)  # 100ms debounce
            instance = TradeSignalHandler._pending_updates.pop(key)
            await TradeSignalHandler.send_trade_update(instance, False, update_type, serializer_class)

    @staticmethod
    async def send_trade_update(
        instance: Any,
        created: bool,
        update_type: str,
        serializer_class: Any
    ):
        """Send trade update notifications to relevant subscriber groups."""
        try:
            if created:  # Skip new trade creation
                return

            trade_data = await TradeUpdateManager.prepare_trade_data(instance, serializer_class, update_type, created)
            plan_config = await sync_to_async(TradeUpdateManager.get_plan_configs)(instance.plan_type)
            if not plan_config.levels:
                return

            trade_time = instance.created_at if hasattr(instance, 'created_at') else timezone.now()
            group_names = await TradeSignalHandler._get_subscriber_groups(plan_config.levels, trade_time)
            
            if not group_names:
                return

            channel_layer = get_channel_layer()
            message = {
                "type": "trade_update",
                "data": {
                    **trade_data,
                    "notification_type": "trade_update",
                    "priority": "high" if instance.status == Trade.Status.ACTIVE else "normal"
                }
            }

            # Send to groups in chunks
            chunk_size = 50
            for i in range(0, len(group_names), chunk_size):
                chunk = group_names[i:i + chunk_size]
                tasks = [channel_layer.group_send(group, message) for group in chunk]
                await asyncio.gather(*tasks)

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Sent {update_type} update to {len(group_names)} subscribers")

        except Exception as e:
            logger.error(f"Failed to send {update_type} update: {str(e)}")


@receiver(post_save, sender=Trade)
def notify_trade_update(sender, instance, created, **kwargs):
    """Signal receiver for stock trade updates."""
    if not created:
        try:
            async_to_sync(TradeSignalHandler.debounce_send)(instance, "stock", CompanySerializer)
        except Exception as e:
            logger.error(f"Failed to notify stock trade update for trade {instance.id}: {str(e)}")


@receiver(post_save, sender=IndexAndCommodityTrade)
def notify_index_trade_update(sender, instance, created, **kwargs):
    """Signal receiver for index/commodity trade updates."""
    if not created:
        try:
            async_to_sync(TradeSignalHandler.debounce_send)(instance, "index", IndexAndCommoditySeraializer)
        except Exception as e:
            logger.error(f"Failed to notify index/commodity trade update for trade {instance.id}: {str(e)}")



# this is done by me sidharth uodated signals

# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from channels.layers import get_channel_layer
# from asgiref.sync import async_to_sync, sync_to_async
# from .models import Trade
# from apps.indexAndCommodity.models import Trade as IndexAndCommodityTrade
# from .serializers.tradeconsumer_serializers import CompanySerializer, IndexAndCommoditySeraializer
# from apps.subscriptions.models import Subscription
# import logging
# from django.utils import timezone
# from functools import lru_cache
# from typing import Dict, List, Any
# from dataclasses import dataclass
# import asyncio

# logger = logging.getLogger(__name__)

# @dataclass
# class PlanConfig:
#     levels: List[str]

# class TradeUpdateManager:

#     @staticmethod
#     @lru_cache(maxsize=3)
#     def get_plan_configs(plan_type: str) -> PlanConfig:
#         configs = {
#             'BASIC': PlanConfig(['BASIC', 'PREMIUM', 'SUPER_PREMIUM']),
#             'PREMIUM': PlanConfig(['PREMIUM', 'SUPER_PREMIUM']),
#             'SUPER_PREMIUM': PlanConfig(['SUPER_PREMIUM'])
#         }
#         return configs.get(plan_type, PlanConfig([]))

#     @staticmethod
#     async def prepare_trade_data(instance: Any, serializer_class: Any, update_type: str, created: bool) -> Dict[str, Any]:
#         parent_object = instance.company if update_type == "stock" else instance.index_and_commodity
#         action = (
#             "created" if created and instance.status == "ACTIVE"
#             else "cancelled" if instance.status in ["CANCELLED", "DELETED", "PENDING", "COMPLETED"]
#             else "updated"
#         )
#         previous_status = instance.tracker.previous('status') if not created else None
#         serializer_data = await sync_to_async(lambda: serializer_class(parent_object).data)()

#         return {
#             "update_type": update_type,
#             "action": action,
#             "data": serializer_data,
#             "plan_type": instance.plan_type,
#             "trade_status": instance.status,
#             "trade_id": instance.id,
#             "is_realtime": True,
#             "previous_status": previous_status,
#         }

# class TradeSignalHandler:
#     _pending_updates = {}

#     @staticmethod
#     @lru_cache(maxsize=128)
#     def _get_subscriber_groups_cached(plan_levels: tuple, timestamp: int) -> List[str]:
#         trade_time = timezone.datetime.fromtimestamp(timestamp, tz=timezone.utc)
#         now = timezone.now()

#         subscriptions = Subscription.objects.filter(
#             plan__name__in=plan_levels,
#             is_active=True,
#             start_date__lte=now,
#             end_date__gte=now,
#             start_date__lte=trade_time  
#         ).values_list('user__id', flat=True)

#         return [f"trade_updates_{user_id}" for user_id in subscriptions]

#     @staticmethod
#     async def _get_subscriber_groups(plan_levels: List[str], trade_time) -> List[str]:
#         return await sync_to_async(TradeSignalHandler._get_subscriber_groups_cached)(
#             tuple(plan_levels), int(trade_time.timestamp())
#         )

#     @staticmethod
#     async def debounce_send(instance, update_type, serializer_class):
#         key = f"{update_type}_{instance.id}"
#         if key not in TradeSignalHandler._pending_updates:
#             TradeSignalHandler._pending_updates[key] = instance
#             await asyncio.sleep(0.1)
#             instance = TradeSignalHandler._pending_updates.pop(key)
#             await TradeSignalHandler.send_trade_update(instance, False, update_type, serializer_class)

#     @staticmethod
#     async def send_trade_update(instance: Any, created: bool, update_type: str, serializer_class: Any):
#         try:
#             if created:
#                 return

#             trade_data = await TradeUpdateManager.prepare_trade_data(instance, serializer_class, update_type, created)
#             plan_config = await sync_to_async(TradeUpdateManager.get_plan_configs)(instance.plan_type)
#             if not plan_config.levels:
#                 return

#             trade_time = instance.created_at if hasattr(instance, 'created_at') else timezone.now()

#             group_names = await TradeSignalHandler._get_subscriber_groups(plan_config.levels, trade_time)
#             if not group_names:
#                 return

#             channel_layer = get_channel_layer()
#             message = {"type": "trade_update", "data": trade_data}

#             chunk_size = 50
#             for i in range(0, len(group_names), chunk_size):
#                 chunk = group_names[i:i + chunk_size]
#                 tasks = [channel_layer.group_send(group, message) for group in chunk]
#                 await asyncio.gather(*tasks)

#             if logger.isEnabledFor(logging.DEBUG):
#                 logger.debug(f"Sent {update_type} update to {len(group_names)} subscribers")

#         except Exception as e:
#             logger.error(f"Failed to send {update_type} update: {str(e)}")

# @receiver(post_save, sender=Trade)
# def notify_trade_update(sender, instance, created, **kwargs):
#     if not created:
#         try:
#             async_to_sync(TradeSignalHandler.debounce_send)(instance, "stock", CompanySerializer)
#         except Exception as e:
#             logger.error(f"Failed to notify stock trade update for trade {instance.id}: {str(e)}")

# @receiver(post_save, sender=IndexAndCommodityTrade)
# def notify_index_trade_update(sender, instance, created, **kwargs):
#     if not created:
#         try:
#             async_to_sync(TradeSignalHandler.debounce_send)(instance, "index", IndexAndCommoditySeraializer)
#         except Exception as e:
#             logger.error(f"Failed to notify index/commodity trade update for trade {instance.id}: {str(e)}")


# # from django.db.models.signals import post_save
# # from django.dispatch import receiver
# # from channels.layers import get_channel_layer
# # from asgiref.sync import async_to_sync, sync_to_async
# # from .models import Trade
# # from apps.indexAndCommodity.models import Trade as IndexAndCommodityTrade
# # from .serializers.tradeconsumer_serializers import CompanySerializer, IndexAndCommoditySeraializer
# # from apps.subscriptions.models import Subscription
# # import logging
# # from django.utils import timezone
# # from functools import lru_cache
# # from typing import Dict, List, Any
# # from dataclasses import dataclass
# # import asyncio

# # logger = logging.getLogger(__name__)

# # @dataclass
# # class PlanConfig:
# #     levels: List[str]

# # class TradeUpdateManager:

# #     @staticmethod
# #     @lru_cache(maxsize=3)
# #     def get_plan_configs(plan_type: str) -> PlanConfig:
# #         configs = {
# #             'BASIC': PlanConfig(['BASIC', 'PREMIUM', 'SUPER_PREMIUM']),
# #             'PREMIUM': PlanConfig(['PREMIUM', 'SUPER_PREMIUM']),
# #             'SUPER_PREMIUM': PlanConfig(['SUPER_PREMIUM'])
# #         }
# #         return configs.get(plan_type, PlanConfig([]))

# #     @staticmethod
# #     async def prepare_trade_data(instance: Any, serializer_class: Any, update_type: str, created: bool) -> Dict[str, Any]:
# #         parent_object = instance.company if update_type == "stock" else instance.index_and_commodity
# #         action = (
# #             "created" if created and instance.status == "ACTIVE"
# #             else "cancelled" if instance.status in ["CANCELLED", "DELETED", "PENDING", "COMPLETED"]
# #             else "updated"
# #         )
# #         previous_status = instance.tracker.previous('status') if not created else None
# #         serializer_data = await sync_to_async(lambda: serializer_class(parent_object).data)()

# #         return {
# #             "update_type": update_type,
# #             "action": action,
# #             "data": serializer_data,
# #             "plan_type": instance.plan_type,
# #             "trade_status": instance.status,
# #             "trade_id": instance.id,
# #             "is_realtime": True,
# #             "previous_status": previous_status,
# #         }

# # class TradeSignalHandler:
# #     _pending_updates = {}

# #     @staticmethod
# #     @lru_cache(maxsize=128)
# #     def _get_subscriber_groups_cached(plan_levels: tuple, timestamp: int) -> List[str]:
# #         trade_time = timezone.datetime.fromtimestamp(timestamp, tz=timezone.utc)
# #         now = timezone.now()

# #         subscriptions = Subscription.objects.filter(
# #             plan__name__in=plan_levels,
# #             is_active=True,
# #             # start_date__lte=now,
# #             end_date__gte=now,
# #             start_date__lte=trade_time  
# #         ).values_list('user__id', flat=True)

# #         return [f"trade_updates_{user_id}" for user_id in subscriptions]

# #     @staticmethod
# #     async def _get_subscriber_groups(plan_levels: List[str], trade_time) -> List[str]:
# #         return await sync_to_async(TradeSignalHandler._get_subscriber_groups_cached)(
# #             tuple(plan_levels), int(trade_time.timestamp())
# #         )

# #     @staticmethod
# #     async def debounce_send(instance, update_type, serializer_class):
# #         key = f"{update_type}_{instance.id}"
# #         if key not in TradeSignalHandler._pending_updates:
# #             TradeSignalHandler._pending_updates[key] = instance
# #             await asyncio.sleep(0.1)
# #             instance = TradeSignalHandler._pending_updates.pop(key)
# #             await TradeSignalHandler.send_trade_update(instance, False, update_type, serializer_class)

# #     @staticmethod
# #     async def send_trade_update(instance: Any, created: bool, update_type: str, serializer_class: Any):
# #         try:
# #             if created:
# #                 return

# #             trade_data = await TradeUpdateManager.prepare_trade_data(instance, serializer_class, update_type, created)
# #             plan_config = await sync_to_async(TradeUpdateManager.get_plan_configs)(instance.plan_type)
# #             if not plan_config.levels:
# #                 return

# #             trade_time = instance.created_at if hasattr(instance, 'created_at') else timezone.now()

# #             group_names = await TradeSignalHandler._get_subscriber_groups(plan_config.levels, trade_time)
# #             if not group_names:
# #                 return

# #             channel_layer = get_channel_layer()
# #             message = {"type": "trade_update", "data": trade_data}

# #             chunk_size = 50
# #             for i in range(0, len(group_names), chunk_size):
# #                 chunk = group_names[i:i + chunk_size]
# #                 tasks = [channel_layer.group_send(group, message) for group in chunk]
# #                 await asyncio.gather(*tasks)

# #             if logger.isEnabledFor(logging.DEBUG):
# #                 logger.debug(f"Sent {update_type} update to {len(group_names)} subscribers")

# #         except Exception as e:
# #             logger.error(f"Failed to send {update_type} update: {str(e)}")

# # @receiver(post_save, sender=Trade)
# # def notify_trade_update(sender, instance, created, **kwargs):
# #     if not created:
# #         try:
# #             async_to_sync(TradeSignalHandler.debounce_send)(instance, "stock", CompanySerializer)
# #         except Exception as e:
# #             logger.error(f"Failed to notify stock trade update for trade {instance.id}: {str(e)}")

# # @receiver(post_save, sender=IndexAndCommodityTrade)
# # def notify_index_trade_update(sender, instance, created, **kwargs):
# #     if not created:
# #         try:
# #             async_to_sync(TradeSignalHandler.debounce_send)(instance, "index", IndexAndCommoditySeraializer)
# #         except Exception as e:
# #             logger.error(f"Failed to notify index/commodity trade update for trade {instance.id}: {str(e)}")
