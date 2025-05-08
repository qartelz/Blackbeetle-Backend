from rest_framework import serializers
from ..models import Trade, Analysis, TradeHistory, Company, Insight
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
    analysis = AnalysisSerializer(read_only=True)
    trade_history = TradeHistorySerializer(source='history', many=True, read_only=True)
    insight = InsightSerializer(read_only=True)

    class Meta:
        model = Trade
        fields = [
            'id', 'trade_type', 'status', 'plan_type',
            'warzone', 'image', 'warzone_history',
            'analysis', 'trade_history', 'insight', 'completed_at', 'created_at', 'updated_at'
        ]

class GroupedTradeSerializer(serializers.ModelSerializer):
    tradingSymbol = serializers.CharField(source='trading_symbol')
    instrumentName = serializers.SerializerMethodField()
    intraday_trade = serializers.SerializerMethodField()
    positional_trade = serializers.SerializerMethodField()
    completed_trade = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()


    class Meta:
        model = Company
        fields = [
            'id', 'tradingSymbol', 'exchange', 'instrumentName', 'completed_trade',
            'intraday_trade', 'positional_trade','created_at',
        ]

 
    def get_instrumentName(self, obj):
        instrument_mapping = {
            'EQUITY': 'EQUITY',
            'FNO_FUT': 'F&O',
            'FNO_CE': 'F&O',
            'FNO_PE': 'F&O',
        }
        return instrument_mapping.get(obj.instrument_type, obj.instrument_type)


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


    def get_completed_trade(self, obj):
        trades = obj.trades.filter(status__in=['COMPLETED'])
        return TradeDetailSerializer(trades, many=True).data if trades.exists() else None
    
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
            return latest_trade.created_at
        return None