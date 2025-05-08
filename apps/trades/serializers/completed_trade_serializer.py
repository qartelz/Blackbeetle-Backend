from rest_framework import serializers
from django.db.models import F
from django.db.models.functions import TruncMonth
from ..models import Trade, TradeHistory, Analysis, Insight, Company

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['trading_symbol', 'exchange', 'instrument_type', 'display_name']

class TradeHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeHistory
        fields = [
            'buy', 'target', 'sl', 'timestamp',
            'risk_reward_ratio', 'potential_profit_percentage',
            'stop_loss_percentage'
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # Convert Decimal fields to float
        decimal_fields = ['buy', 'target', 'sl', 'risk_reward_ratio', 
                         'potential_profit_percentage', 'stop_loss_percentage']
        for field in decimal_fields:
            if field in representation and representation[field] is not None:
                representation[field] = float(representation[field])
        return representation

class TradeListItemSerializer(serializers.ModelSerializer):
    """Minimal serializer for trade list view"""
    trading_symbol = serializers.CharField(source='company.trading_symbol')
    exchange = serializers.CharField(source='company.exchange')
    analysis_status = serializers.CharField(source='analysis.status', default=None)
    latest_price_points = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        fields = [
            'id', 'trading_symbol', 'exchange', 'trade_type',
            'status', 'analysis_status', 'completed_at',
            'latest_price_points'
        ]

    def get_latest_price_points(self, obj):
        latest_history = obj.history.order_by('-timestamp').first()
        if latest_history:
            return {
                'buy': float(latest_history.buy),
                'target': float(latest_history.target),
                'sl': float(latest_history.sl)
            }
        return None

class TradeDetailSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    history = serializers.SerializerMethodField()
    analysis = serializers.SerializerMethodField()
    insight = serializers.SerializerMethodField()
    warzone = serializers.FloatField()

    class Meta:
        model = Trade
        fields = [
            'id', 'trade_type', 'status', 'plan_type', 'completed_at',
            'company', 'history', 'analysis', 'insight', 'warzone',
            'warzone_history', 'image'
        ]

    def get_history(self, obj):
        histories = obj.history.order_by('timestamp')
        latest_history = histories.last()
        return {
            'entries': TradeHistorySerializer(histories, many=True).data,
            'latest_points': TradeHistorySerializer(latest_history).data if latest_history else None
        }

    def get_analysis(self, obj):
        if hasattr(obj, 'analysis'):
            return {
                'bull_scenario': obj.analysis.bull_scenario,
                'bear_scenario': obj.analysis.bear_scenario,
                'status': obj.analysis.status,
                'completed_at': obj.analysis.completed_at
            }
        return None

    def get_insight(self, obj):
        if hasattr(obj, 'insight'):
            request = self.context.get('request')
            return {
                'prediction_image': request.build_absolute_uri(obj.insight.prediction_image.url) 
                    if obj.insight.prediction_image else None,
                'actual_image': request.build_absolute_uri(obj.insight.actual_image.url) 
                    if obj.insight.actual_image else None,
                'prediction_description': obj.insight.prediction_description,
                'actual_description': obj.insight.actual_description,
                'accuracy_score': obj.insight.accuracy_score,
                'analysis_result': obj.insight.analysis_result
            }
        return None
