from rest_framework import serializers
from ..models import IndexAndCommodity, Trade, Analysis, TradeHistory, Insight


class TradeHistoryDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeHistory
        fields = [
            'buy', 'target', 'sl', 'timestamp',
            'risk_reward_ratio', 'potential_profit_percentage',
            'stop_loss_percentage'
        ]

class InsightDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insight
        fields = [
            'prediction_image', 'actual_image',
            'prediction_description', 'actual_description',
            'accuracy_score', 'analysis_result'
        ]

class AnalysisDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = [
            'bull_scenario', 'bear_scenario', 'status',
            'completed_at', 'created_at', 'updated_at'
        ]

class TradeDetailSerializer(serializers.ModelSerializer):
    trade_history = TradeHistoryDetailSerializer(source='index_and_commodity_history', many=True, read_only=True)
    analysis = AnalysisDetailSerializer(source='index_and_commodity_analysis', read_only=True)
    insight = InsightDetailSerializer(source='index_and_commodity_insight', read_only=True)

    class Meta:
        model = Trade
        fields = [
            'id', 'trade_type', 'status', 'plan_type',
            'warzone', 'image', 'warzone_history',
            'analysis', 'trade_history', 'insight','completed_at','created_at', 'updated_at'
        ]

class IndexAndCommodityTradesSerializer(serializers.ModelSerializer):
    intraday_trade = serializers.SerializerMethodField()
    positional_trade = serializers.SerializerMethodField()
    created_at =serializers.SerializerMethodField()

    
    class Meta:
        model = IndexAndCommodity
        fields = [
            'id', 'tradingSymbol', 'exchange', 'instrumentName', 
            'intraday_trade', 'positional_trade', 'created_at', 
        ]
    
    def get_intraday_trade(self, obj):
        trade = obj.trades.filter(
            trade_type=Trade.TradeType.INTRADAY,
            status__in=['ACTIVE']
        ).first()
        return TradeDetailSerializer(trade).data if trade else None
    
    def get_positional_trade(self, obj):
        trade = obj.trades.filter(
            trade_type=Trade.TradeType.POSITIONAL,
            status__in=['ACTIVE']
        ).first()
        return TradeDetailSerializer(trade).data if trade else None
    
    def get_created_at(self, obj):
        # Fetch all active intraday and positional trades
        active_trades = obj.trades.filter(
            status__in=['ACTIVE'],
            trade_type__in=[Trade.TradeType.INTRADAY, Trade.TradeType.POSITIONAL]
        )
        if active_trades.exists():
            # Get the trade with the latest created_at
            latest_trade = active_trades.latest('created_at')
            return latest_trade.created_at
        return None