# import json
# from channels.generic.websocket import AsyncWebsocketConsumer
# from channels.db import database_sync_to_async
# from django.contrib.auth.models import AnonymousUser
# from django.utils import timezone
# from .models import IndexAndCommodity
# from trades.models import Company
# from .serializers.grouped_trades_serializers import  IndexAndCommodityTradesSerializer
# from trades.serializers.trade_serializers import CompanyTradesSerializer
# from ..filters import GroupedTradeFilter as CompanyTradeFilter, GroupedTradeFilter as IndexAndCommodityTradeFilter

# class GroupedTradesConsumer(AsyncWebsocketConsumer):
#     async def connect(self): 
#         user = self.scope["user"]
#         if user is None or isinstance(user, AnonymousUser):
#             await self.close()
#             return
        
#         # Extract query parameters from the WebSocket URL
#         query_params = self.scope['query_string'].decode('utf-8')
#         self.filters = self.parse_query_params(query_params)
        
#         await self.accept()
#         await self.channel_layer.group_add(
#             f"user_{user.id}_trades",
#             self.channel_name
#         )
#         # Send initial filtered data upon connection
#         grouped_trades = await self.get_grouped_trades(user, self.filters)
#         await self.send(text_data=json.dumps(grouped_trades))

#     async def disconnect(self, close_code):
#         user = self.scope["user"]
#         if user:
#             await self.channel_layer.group_discard(
#                 f"user_{user.id}_trades",
#                 self.channel_name
#             )

#     @database_sync_to_async
#     def get_grouped_trades(self, user, filters):
#         current_date = timezone.now().date()
#         current_subscription = user.subscriptions.filter(
#             is_active=True,
#             start_date__lte=current_date,
#             end_date__gte=current_date
#         ).first()

#         if not current_subscription:
#             return {"trades_app": [], "index_commodity_app": []}

#         plan_type = current_subscription.plan.name
#         plan_filters = {
#             'BASIC': ['BASIC'],
#             'PREMIUM': ['BASIC', 'PREMIUM'],
#             'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
#         }
#         allowed_plans = plan_filters.get(plan_type, [])

#         # Apply filters to Trades App Data
#         trades_queryset = Company.objects.filter(
#             trades__status__in=['ACTIVE', 'COMPLETED'],
#             trades__created_at__date__gte=current_subscription.start_date,
#             trades__created_at__date__lte=current_subscription.end_date,
#             trades__plan_type__in=allowed_plans
#         ).distinct()
#         trades_filter = CompanyTradeFilter(filters, queryset=trades_queryset)
#         trades_queryset = trades_filter.qs

#         # Apply filters to IndexAndCommodity App Data
#         index_commodity_queryset = IndexAndCommodity.objects.filter(
#             index_and_commodity_trades__status__in=['ACTIVE', 'COMPLETED'],
#             index_and_commodity_trades__created_at__date__gte=current_subscription.start_date,
#             index_and_commodity_trades__created_at__date__lte=current_subscription.end_date,
#             index_and_commodity_trades__plan_type__in=allowed_plans
#         ).distinct()
#         index_commodity_filter = IndexAndCommodityTradeFilter(filters, queryset=index_commodity_queryset)
#         index_commodity_queryset = index_commodity_filter.qs

#         # Serialize filtered data
#         trades_serializer = CompanyTradesSerializer(trades_queryset, many=True)
#         index_commodity_serializer = IndexAndCommodityTradesSerializer(index_commodity_queryset, many=True)

#         return {
#             'trades_app': trades_serializer.data,
#             'index_commodity_app': index_commodity_serializer.data
#         }

#     async def send_grouped_trades(self, event):
#         await self.send(text_data=json.dumps(event['data']))

#     def parse_query_params(self, query_string):
#         """Parse query parameters from the WebSocket URL."""
#         params = {}
#         for param in query_string.split('&'):
#             key, value = param.split('=')
#             params[key] = value
#         return params