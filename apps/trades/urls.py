
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .controllers.company_views import CompanyViewSet
from .controllers.trade_views import TradeViewSet
from .controllers.trade_history_views import TradeHistoryViewSet
from .controllers.grouptrade_views import GroupedTradeViewSet
from .controllers.freecall_views import FreeCallTradeViewSet, PublicFreeCallTradeViewSet
from .controllers.insight_views import InsightViewSet
from .trade_updates.views import TradeUpdatesSSE
from .controllers.complete_trade_views import TradeViewSet as CompleteTradeViewSet
from .controllers.completed_trade_old_views import CompletedTradeViewSet

router = DefaultRouter()
router.register('companies', CompanyViewSet)
router.register('trades', TradeViewSet)
router.register(r'staff/free-call-trades', FreeCallTradeViewSet, basename='staff-free-call-trades')
router.register(r'public/free-call-trade', PublicFreeCallTradeViewSet, basename='public-free-call-trade')
router.register(r'insights', InsightViewSet)
router.register(r'completed-trades', CompleteTradeViewSet, basename='completed-trade')
router.register(r'completed-trades-old', CompletedTradeViewSet, basename='completed-trade-old')

trade_history_list = TradeHistoryViewSet.as_view({
    'get': 'list',
    'post': 'create'
})
trade_history_detail = TradeHistoryViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy'
})
grouped_trade_list = GroupedTradeViewSet.as_view({
    'get': 'list',
})



redis_sse_urlpatterns = [
    path('trade-updates/', TradeUpdatesSSE.as_view(), name='trade-updates-sse')
]

urlpatterns = [
    path('', include(router.urls)),
    path('trades/<int:trade_pk>/history/', trade_history_list, name='trade-history-list'),
    path('trades/<int:trade_pk>/history/<int:pk>/', trade_history_detail, name='trade-history-detail'),
    path('grouped-trades/', grouped_trade_list, name='grouped-trade-list'),
]+redis_sse_urlpatterns
# from django.urls import path,include
# from .views import (
#     trade_history_views, trade_views,
#     insight_views, analysis_views,
#     company_views,
# )
# from rest_framework.routers import DefaultRouter

# router = DefaultRouter()
# router.register(r'companies', company_views.CompanyViewSet, basename='company')
# router.register('trades-view', trade_views.TradeViewSet, basename='trade-view')

# urlpatterns = [
#     path('', include(router.urls)),
#     path('trades/', trade_views.TradeListView.as_view(), name='trade-list'),
#     path('trades/<int:pk>/', trade_views.TradeDetailView.as_view(), name='trade-detail'),
#     path('trades/<int:trade_pk>/history/', trade_history_views.TradeHistoryView.as_view(), name='trade-history'),
#     path('trades/<int:trade_pk>/history/update/', trade_history_views.TradeHistoryUpdateView.as_view(), name='trade-history-update'),
#     path('trades/<int:trade_pk>/insight/', insight_views.InsightDetailView.as_view(), name='insight-list'),
#     path('insights/<int:pk>/', insight_views.InsightDetailView.as_view(), name='insight-detail'),
#     path('trades/<int:trade_pk>/analysis/', analysis_views.AnalysisView.as_view(), name='trade-analysis'),
#     path('trades/filter/', trade_views.FilteredTradeListView.as_view(), name='filtered-trade-list'),
#     path('companies/search/', company_views.CompanyViewSet.as_view({'get': 'search'}), name='company-search'),
#     path('create-companies/upload-csv/', company_views.CompanyCSVUploadView.as_view(), name='company-csv-upload'),
#     path('tasks/<str:task_id>/status/', company_views.TaskStatusView.as_view(), name='task-status'),
#     path('free-call-trades/', trade_views.FreeCallTradeListView.as_view(), name='free-call-trade'),

# ]