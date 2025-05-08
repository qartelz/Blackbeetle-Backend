from rest_framework import serializers
from ..models import (
    Company, Trade, TradeHistory, 
    Analysis, Insight, FreeCallTrade
)
from apps.indexAndCommodity.models import IndexAndCommodity ,Trade as IndexAndCommodityTrade,TradeHistory as IndexAndCommodityTradeHistory,Analysis as IndexAndCommodityAnalysis,Insight as IndexAndCommodityInsight

class TradeHistorySerializer(serializers.ModelSerializer):
    risk_reward_ratio = serializers.SerializerMethodField()
    potential_profit_percentage = serializers.SerializerMethodField()
    stop_loss_percentage = serializers.SerializerMethodField()

    class Meta:
        model = TradeHistory
        fields = [
            'buy', 'target', 'sl', 'timestamp','risk_reward_ratio', 'potential_profit_percentage', 'stop_loss_percentage'
            
        ]

    def get_risk_reward_ratio(self, obj):
        return obj.risk_reward_ratio

    def get_potential_profit_percentage(self, obj):
        return obj.potential_profit_percentage

    def get_stop_loss_percentage(self, obj):
        return obj.stop_loss_percentage

class AnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = ['bull_scenario', 'bear_scenario', 'status', 
                 'completed_at', 'created_at', 'updated_at']

class InsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insight
        fields = [
            'prediction_image', 'actual_image', 
            'prediction_description', 'actual_description',
            'accuracy_score', 'analysis_result'
        ]

class TradeSerializer(serializers.ModelSerializer):
    analysis = AnalysisSerializer(required=False)
    trade_history = TradeHistorySerializer(source='history', many=True,required=False)
    insight = InsightSerializer(required=False)

    class Meta:
        model = Trade
        fields = [
            'id', 'trade_type', 'status', 'plan_type',
            'warzone', 'image', 'warzone_history',
            'analysis', 'trade_history', 'insight'
        ]

class CompanySerializer(serializers.ModelSerializer):
    tradingSymbol = serializers.CharField(source='trading_symbol')
    instrumentName = serializers.CharField(source='instrument_type')
    intraday_trade = serializers.SerializerMethodField()
    positional_trade = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'tradingSymbol', 'exchange', 'instrumentName',
            'intraday_trade', 'positional_trade', 'created_at', 'updated_at'
        ]

    def get_intraday_trade(self, obj):
        trade = obj.trades.filter(
            trade_type=Trade.TradeType.INTRADAY,
            status=Trade.Status.ACTIVE
        ).first()
        return TradeSerializer(trade).data if trade else None

    def get_positional_trade(self, obj):
        trade = obj.trades.filter(
            trade_type=Trade.TradeType.POSITIONAL,
            status=Trade.Status.ACTIVE
        ).first()
        return TradeSerializer(trade).data if trade else None
    
    def get_created_at(self, obj):
        # Fetch all active intraday and positional trades
        active_trades = obj.trades.filter(
            status__in=['ACTIVE'],
            trade_type__in=[Trade.TradeType.INTRADAY, Trade.TradeType.POSITIONAL]
        )
        print(active_trades,'active_trades')
        if active_trades.exists():
            # Get the trade with the latest created_at
            latest_trade = active_trades.latest('created_at')
            return str(latest_trade.created_at)
        return None
    



# ----------------------------------------------------------------index-and-commodity----------------------------------------------------------------------#



class IndexAndCommodityTradeHistorySerializer(serializers.ModelSerializer):
    risk_reward_ratio = serializers.SerializerMethodField()
    potential_profit_percentage = serializers.SerializerMethodField()
    stop_loss_percentage = serializers.SerializerMethodField()

    class Meta:
        model = IndexAndCommodityTradeHistory
        fields = [
            'buy', 'target', 'sl', 'timestamp','risk_reward_ratio', 'potential_profit_percentage', 'stop_loss_percentage'
            
        ]

    def get_risk_reward_ratio(self, obj):
        return obj.risk_reward_ratio

    def get_potential_profit_percentage(self, obj):
        return obj.potential_profit_percentage

    def get_stop_loss_percentage(self, obj):
        return obj.stop_loss_percentage

class IndexAndCommodityAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndexAndCommodityAnalysis
        fields = ['bull_scenario', 'bear_scenario', 'status', 
                 'completed_at', 'created_at', 'updated_at']

class IndexAndCommodityInsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndexAndCommodityInsight
        fields = [
            'prediction_image', 'actual_image', 
            'prediction_description', 'actual_description',
            'accuracy_score', 'analysis_result'
        ]

class IndexAndCommodityTradeSerializer(serializers.ModelSerializer):
    analysis = IndexAndCommodityAnalysisSerializer(required=False)
    trade_history = IndexAndCommodityTradeHistorySerializer(source='index_and_commodity_history', many=True,required=False)
    insight = IndexAndCommodityInsightSerializer(required=False)

    class Meta:
        model = IndexAndCommodityTrade
        fields = [
            'id', 'trade_type', 'status', 'plan_type',
            'warzone', 'image', 'warzone_history',
            'analysis', 'trade_history', 'insight'
        ]



class IndexAndCommoditySeraializer(serializers.ModelSerializer):

    intraday_trade = serializers.SerializerMethodField()
    positional_trade = serializers.SerializerMethodField()
    created_at =serializers.SerializerMethodField()

    class Meta:
        model = IndexAndCommodity
        fields = [
            'id', 'tradingSymbol', 'exchange', 'instrumentName',
            'intraday_trade', 'positional_trade', 'created_at', 'updated_at'
        ]

    def get_intraday_trade(self, obj):
        trade = obj.trades.filter(
            trade_type=Trade.TradeType.INTRADAY,
            status=Trade.Status.ACTIVE
        ).first()
        return IndexAndCommodityTradeSerializer(trade).data if trade else None

    def get_positional_trade(self, obj):
        trade = obj.trades.filter(
            trade_type=Trade.TradeType.POSITIONAL,
            status=Trade.Status.ACTIVE
        ).first()
        return IndexAndCommodityTradeSerializer(trade).data if trade else None


    def get_created_at(self, obj):
        # Fetch all active intraday and positional trades
        active_trades = obj.trades.filter(
            status__in=['ACTIVE'],
            trade_type__in=[Trade.TradeType.INTRADAY, Trade.TradeType.POSITIONAL]
        )
        print(active_trades,'active_trades')
        if active_trades.exists():
            # Get the trade with the latest created_at
            latest_trade = active_trades.latest('created_at')
            return str(latest_trade.created_at)
        return None

