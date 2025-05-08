from django.urls import path
from .views import AccuracyCreateView,AccuracyListCreateView,ActiveTradesView,TradeStatisticsView,CompletedTradesView,AccuracyByTradeView

urlpatterns = [
    path('create-accuracy/', AccuracyCreateView.as_view(), name='accuracy-create'),
    path('accuracy/', AccuracyListCreateView.as_view(), name='accuracy'),
    path('trade/<int:trade_id>/', AccuracyByTradeView.as_view(), name='accuracy-by-trade'),

    # path("stats/", ActiveTradesView.as_view(), name="accuracy-stats"),
    path("statistics/", TradeStatisticsView.as_view(), name="trade-statistics"),
    path("active/", ActiveTradesView.as_view(), name="active-trades"),
    path("completed/", CompletedTradesView.as_view(), name="completed-trades"),
]