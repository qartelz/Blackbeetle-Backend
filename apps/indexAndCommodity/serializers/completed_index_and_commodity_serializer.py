from rest_framework import serializers
from django.db.models import F
from django.db.models.functions import TruncMonth
from ..models import Trade, TradeHistory, Analysis, Insight, IndexAndCommodity

class CompanySerializer(serializers.ModelSerializer):
    trading_symbol = serializers.CharField(source='tradingSymbol')
    instrument_type = serializers.CharField(source='instrumentName')
    display_name = serializers.CharField(source='tradingSymbol')
    
    class Meta:
        model = IndexAndCommodity
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
        decimal_fields = ['buy', 'target', 'sl', 'risk_reward_ratio', 
                         'potential_profit_percentage', 'stop_loss_percentage']
        for field in decimal_fields:
            if field in representation and representation[field] is not None:
                representation[field] = float(representation[field])
        return representation

class TradeListItemSerializer(serializers.ModelSerializer):
    """Minimal serializer for trade list view"""
    trading_symbol = serializers.CharField(source='index_and_commodity.tradingSymbol')
    exchange = serializers.CharField(source='index_and_commodity.exchange')
    analysis_status = serializers.CharField(source='index_and_commodity_analysis.status', default=None)
    latest_price_points = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        fields = [
            'id', 'trading_symbol', 'exchange', 'trade_type',
            'status', 'analysis_status', 'completed_at',
            'latest_price_points'
        ]

    def get_latest_price_points(self, obj):
        latest_history = obj.index_and_commodity_history.order_by('-timestamp').first()
        if latest_history:
            return {
                'buy': float(latest_history.buy),
                'target': float(latest_history.target),
                'sl': float(latest_history.sl)
            }
        return None

class TradeDetailSerializer(serializers.ModelSerializer):
    company = CompanySerializer(source='index_and_commodity', read_only=True)
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
        histories = obj.index_and_commodity_history.order_by('timestamp')
        latest_history = histories.last()
        return {
            'entries': TradeHistorySerializer(histories, many=True).data,
            'latest_points': TradeHistorySerializer(latest_history).data if latest_history else None
        }

    def get_analysis(self, obj):
        if hasattr(obj, 'index_and_commodity_analysis'):
            return {
                'bull_scenario': obj.index_and_commodity_analysis.bull_scenario,
                'bear_scenario': obj.index_and_commodity_analysis.bear_scenario,
                'status': obj.index_and_commodity_analysis.status,
                'completed_at': obj.index_and_commodity_analysis.completed_at
            }
        return None

    def get_insight(self, obj):
        if hasattr(obj, 'index_and_commodity_insight'):
            request = self.context.get('request')
            return {
                'prediction_image': request.build_absolute_uri(obj.index_and_commodity_insight.prediction_image.url) 
                    if obj.index_and_commodity_insight.prediction_image else None,
                'actual_image': request.build_absolute_uri(obj.index_and_commodity_insight.actual_image.url) 
                    if obj.index_and_commodity_insight.actual_image else None,
                'prediction_description': obj.index_and_commodity_insight.prediction_description,
                'actual_description': obj.index_and_commodity_insight.actual_description,
                'accuracy_score': obj.index_and_commodity_insight.accuracy_score,
                'analysis_result': obj.index_and_commodity_insight.analysis_result
            }
        return None