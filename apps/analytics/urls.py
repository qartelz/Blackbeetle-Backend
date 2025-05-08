from django.urls import path
from .views import (
    DashboardAnalyticsView, TradeAnalyticsView,
    TimeSeriesAnalyticsView, RecentTradesView, UserMetricsView
)

urlpatterns = [
    # path('dashboard/', DashboardAnalyticsView.as_view(), name='dashboard-analytics'),
    # path('trades/', TradeAnalyticsView.as_view(), name='trade-analytics'),
    # path('time-series/', TimeSeriesAnalyticsView.as_view(), name='time-series-analytics'),
    # path('recent-trades/', RecentTradesView.as_view(), name='recent-trades'),
    # path('user-metrics/', UserMetricsView.as_view(), name='user-metrics'),
]