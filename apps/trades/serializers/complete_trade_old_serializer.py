# from rest_framework import serializers
# from ..models import Trade, Analysis, TradeHistory, Company, Insight
# from asgiref.sync import sync_to_async

# class TradeHistorySerializer(serializers.ModelSerializer):
#     class Meta:
#         model = TradeHistory
#         fields = [
#             'buy', 'target', 'sl', 'timestamp',
#             'risk_reward_ratio', 'potential_profit_percentage',
#             'stop_loss_percentage'
#         ]

#     def to_representation(self, instance):
#         representation = super().to_representation(instance)
#         # Convert Decimal fields to float
#         for field in ['buy', 'target', 'sl', 'risk_reward_ratio', 'potential_profit_percentage', 'stop_loss_percentage']:
#             if field in representation and representation[field] is not None:
#                 representation[field] = float(representation[field])
#         return representation

# class AnalysisSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Analysis
#         fields = [
#             'bull_scenario', 'bear_scenario', 'status',
#             'completed_at', 'created_at', 'updated_at'
#         ]

# class InsightSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Insight
#         fields = [
#             'prediction_image', 'actual_image',
#             'prediction_description', 'actual_description',
#             'accuracy_score', 'analysis_result'
#         ]

# class TradeDetailSerializer(serializers.ModelSerializer):
#     analysis = AnalysisSerializer(read_only=True)
#     trade_history = TradeHistorySerializer(source='history', many=True, read_only=True)
#     insight = InsightSerializer(read_only=True)

#     class Meta:
#         model = Trade
#         fields = [
#             'id', 'trade_type', 'status', 'plan_type',
#             'warzone', 'image', 'warzone_history',
#             'analysis', 'trade_history', 'insight', 'completed_at'
#         ]

# class CompletedTradeSerializer(serializers.ModelSerializer):
#     tradingSymbol = serializers.CharField(source='trading_symbol')
#     instrumentName = serializers.SerializerMethodField()
#     completed_trade = serializers.SerializerMethodField()
#     created_at = serializers.DateTimeField(format='%Y-%m-%dT%H:%M:%S.%fZ')
#     updated_at = serializers.DateTimeField(format='%Y-%m-%dT%H:%M:%S.%fZ')

#     class Meta:
#         model = Company
#         fields = [
#             'id', 'tradingSymbol', 'exchange', 'instrumentName', 'completed_trade', 'created_at', 'updated_at'
#         ]

 
#     def get_instrumentName(self, obj):
#         instrument_mapping = {
#             'EQUITY': 'EQUITY',
#             'FNO_FUT': 'F&O',
#             'FNO_CE': 'F&O',
#             'FNO_PE': 'F&O',
#         }
#         return instrument_mapping.get(obj.instrument_type, obj.instrument_type)

    


#     # def get_completed_trade(self, obj):
#     #     trades = obj.trades.filter(status__in=['COMPLETED'])
#     #     return TradeDetailSerializer(trades, many=True).data if trades.exists() else None
    

#     def get_completed_trade(self, obj):
#         """
#         Returns a list of completed trades. 
#         If intraday trades exist, they are returned; otherwise, positional trades are returned.
#         """
#         intraday_trade = obj.trades.filter(
#             trade_type=Trade.TradeType.INTRADAY,
#             status='COMPLETED'
#         )
#         if intraday_trade.exists():
#             return TradeDetailSerializer(intraday_trade, many=True).data

#         positional_trade = obj.trades.filter(
#             trade_type=Trade.TradeType.POSITIONAL,
#             status='COMPLETED'
#         )
#         if positional_trade.exists():
#             return TradeDetailSerializer(positional_trade, many=True).data

#         return []  # Return an empty list if no completed trades exist


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
            'analysis', 'trade_history', 'insight', 'updated_at', 'created_at', 'completed_at'
        ]


    

class TradeListItemSerializer(serializers.ModelSerializer):
    tradingSymbol = serializers.CharField(source='company.trading_symbol')
    instrumentName = serializers.CharField(source='company.instrument_type')
    exchange = serializers.CharField(source='company.exchange')
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