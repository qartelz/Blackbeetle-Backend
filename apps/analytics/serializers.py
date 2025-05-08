from rest_framework import serializers
from django.db.models import Count, Avg
from django.utils import timezone
from datetime import timedelta
from ..trades.models import Trade, TradeHistory, Analysis, Insight
from ..users.models import User

class TradeAnalyticsSerializer(serializers.Serializer):
    total_trades = serializers.IntegerField()
    active_trades = serializers.IntegerField()
    completed_trades = serializers.IntegerField()
    cancelled_trades = serializers.IntegerField()
    average_accuracy = serializers.FloatField()

class TimeSeriesDataSerializer(serializers.Serializer):
    date = serializers.DateField()
    trade_count = serializers.IntegerField()

class RecentTradeSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name')
    company_name = serializers.CharField(source='company.name')
    analysis_status = serializers.CharField(source='analysis.status', default='N/A')
    insight_accuracy = serializers.FloatField(source='insight.accuracy_score', default=0)

    class Meta:
        model = Trade
        fields = ['id', 'user_name', 'company_name', 'status', 'created_at', 
                 'analysis_status', 'insight_accuracy']

class UserTypeMetricsSerializer(serializers.Serializer):
    b2b_users = serializers.IntegerField()
    b2b_admins = serializers.IntegerField()
    b2c_users = serializers.IntegerField()
    total_users = serializers.IntegerField()