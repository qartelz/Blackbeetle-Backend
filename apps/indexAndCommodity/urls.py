from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views.indexandcommodity_views import IndexAndCommodityViewSet
from .views.grouped_trades_views import GroupedTradeViewSet
from .views.trade_related_views import TradeViewSet
from .views.trade_history_views import TradeHistoryViewSet
from .views.insight_views import InsightViewSet
from .views.index_and_commodity_completed_views import IndexAndCommodityCompletedViewSet
from .views.completed_trade_old_views import CompletedTradeViewSet

router = DefaultRouter()
router.register(r'indices', IndexAndCommodityViewSet, basename='index-and-commodity')
router.register(r'trades', TradeViewSet)
router.register(r'grouped-trades', GroupedTradeViewSet, basename='grouped-trades')
router.register(r'trade-histories', TradeHistoryViewSet)
router.register(r'insights', InsightViewSet)
router.register(r'completed-trades', IndexAndCommodityCompletedViewSet, basename='completed-trades')
router.register(r'completed-trades-old', CompletedTradeViewSet, basename='completed-trade-old')


urlpatterns = [
    path('', include(router.urls)),
]