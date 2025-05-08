
from rest_framework import serializers
from ..models import Trade, Analysis, TradeHistory, IndexAndCommodity as Company, Insight
from asgiref.sync import sync_to_async

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
        for field in ['buy', 'target', 'sl', 'risk_reward_ratio', 'potential_profit_percentage', 'stop_loss_percentage']:
            if field in representation and representation[field] is not None:
                representation[field] = float(representation[field])
        return representation

class AnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = [
            'bull_scenario', 'bear_scenario', 'status',
            'completed_at', 'created_at', 'updated_at'
        ]

class InsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insight
        fields = [
            'prediction_image', 'actual_image',
            'prediction_description', 'actual_description',
            'accuracy_score', 'analysis_result'
        ]

class TradeDetailSerializer(serializers.ModelSerializer):
    analysis = AnalysisSerializer(source='index_and_commodity_analysis', read_only=True)
    trade_history = TradeHistorySerializer(source='index_and_commodity_history', many=True, read_only=True)
    insight = InsightSerializer(source ='index_and_commodity_insight',read_only=True)

    class Meta:
        model = Trade
        fields = [
            'id', 'trade_type', 'status', 'plan_type',
            'warzone', 'image', 'warzone_history',
            'analysis', 'trade_history', 'insight', 'updated_at', 'created_at', 'completed_at'
        ]


    

class TradeListItemSerializer(serializers.ModelSerializer):
    tradingSymbol = serializers.CharField(source='index_and_commodity.tradingSymbol')
    instrumentName = serializers.CharField(source='index_and_commodity.instrumentName')
    exchange = serializers.CharField(source='index_and_commodity.exchange')
    intraday_trade = serializers.SerializerMethodField()
    positional_trade = serializers.SerializerMethodField()
    updated_at = serializers.DateTimeField(format='%Y-%m-%dT%H:%M:%S.%fZ') 
    created_at = serializers.DateTimeField(format='%Y-%m-%dT%H:%M:%S.%fZ')

    class Meta:
        model = Trade
        fields = [
            'id', 'tradingSymbol', 'exchange', 'instrumentName', 
            'positional_trade', 'intraday_trade', 'updated_at', 'created_at'
        ]

    def get_intraday_trade(self, obj):
        """
        Return trade details if this is a completed intraday trade
        """
        if obj.trade_type == 'INTRADAY' and obj.status == 'COMPLETED':
            return TradeDetailSerializer(obj).data
        return None

    def get_positional_trade(self, obj):
        """
        Return trade details if this is a completed positional trade
        """
        if obj.trade_type == 'POSITIONAL' and obj.status == 'COMPLETED':
            return TradeDetailSerializer(obj).data
        return None