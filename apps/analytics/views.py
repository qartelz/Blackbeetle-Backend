from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.utils import timezone
from django.db.models import Count, Avg, Q
from django.core.cache import cache
from datetime import timedelta
from .serializers import (
    TradeAnalyticsSerializer, TimeSeriesDataSerializer,
    RecentTradeSerializer, UserTypeMetricsSerializer
)
from ..trades.models import Trade, TradeHistory, Analysis, Insight
from ..users.models import User

class DashboardAnalyticsView(APIView):
    # permission_classes = [IsAdminUser]

    def get(self, request):
        """
        Get all dashboard analytics data in a single API call
        """
        return Response({
            'trade_analytics': TradeAnalyticsSerializer(self.get_trade_analytics()).data,
            'time_series_data': TimeSeriesDataSerializer(self.get_time_series_data(), many=True).data,
            'recent_trades': RecentTradeSerializer(self.get_recent_trades(), many=True).data,
            'user_metrics': UserTypeMetricsSerializer(self.get_user_metrics()).data
        })

    def get_trade_analytics(self):
        cache_key = 'trade_analytics'
        cached_data = cache.get(cache_key)

        if cached_data:
            return cached_data

        analytics = {
            'total_trades': Trade.objects.count(),
            'active_trades': Trade.objects.filter(status='ACTIVE').count(),
            'completed_trades': Trade.objects.filter(status='COMPLETED').count(),
            'cancelled_trades': Trade.objects.filter(status='CANCELLED').count(),
            'average_accuracy': Insight.objects.filter(
                accuracy_score__isnull=False
            ).aggregate(Avg('accuracy_score'))['accuracy_score__avg'] or 0
        }

        cache.set(cache_key, analytics, 300)  # Cache for 5 minutes
        return analytics

    def get_time_series_data(self):
        cache_key = 'trade_time_series'
        cached_data = cache.get(cache_key)

        if cached_data:
            return cached_data

        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        trades = Trade.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).values('created_at__date').annotate(
            trade_count=Count('id')
        ).order_by('created_at__date')

        data = [
            {
                'date': item['created_at__date'],
                'trade_count': item['trade_count']
            }
            for item in trades
        ]

        cache.set(cache_key, data, 300)  # Cache for 5 minutes
        return data

    def get_recent_trades(self):
        trades = Trade.objects.select_related(
            'user', 'company', 'analysis', 'insight'
        ).order_by('-created_at')[:10]
        return trades

    def get_user_metrics(self):
        cache_key = 'user_metrics'
        cached_data = cache.get(cache_key)

        if cached_data:
            return cached_data

        metrics = {
            'b2b_users': User.objects.filter(user_type=User.UserType.B2B_USER).count(),
            'b2b_admins': User.objects.filter(user_type=User.UserType.B2B_ADMIN).count(),
            'b2c_users': User.objects.filter(user_type=User.UserType.B2C).count(),
            'total_users': User.objects.count()
        }

        cache.set(cache_key, metrics, 300)  # Cache for 5 minutes
        return metrics

class TradeAnalyticsView(APIView):
    # permission_classes = [IsAdminUser]

    def get(self, request):
        """
        Get trade analytics data
        """
        analytics = DashboardAnalyticsView().get_trade_analytics()
        serializer = TradeAnalyticsSerializer(analytics)
        return Response(serializer.data)

class TimeSeriesAnalyticsView(APIView):
    # permission_classes = [IsAdminUser]

    def get(self, request):
        """
        Get time series data for trades
        """
        data = DashboardAnalyticsView().get_time_series_data()
        serializer = TimeSeriesDataSerializer(data, many=True)
        return Response(serializer.data)

class RecentTradesView(APIView):
    # permission_classes = [IsAdminUser]

    def get(self, request):
        """
        Get recent trades with related data
        """
        trades = DashboardAnalyticsView().get_recent_trades()
        serializer = RecentTradeSerializer(trades, many=True)
        return Response(serializer.data)

class UserMetricsView(APIView):
    # permission_classes = [IsAdminUser]

    def get(self, request):
        """
        Get user metrics by type
        """
        metrics = DashboardAnalyticsView().get_user_metrics()
        serializer = UserTypeMetricsSerializer(metrics)
        return Response(serializer.data)