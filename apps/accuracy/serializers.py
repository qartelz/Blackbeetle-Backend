from rest_framework import serializers
from .models import Accuracy
from apps.trades.models import Trade,TradeHistory, Analysis


class AccuracySerializer(serializers.ModelSerializer):
    class Meta:
        model = Accuracy
        
        fields = ['id', 'trade', 'target_hit', 'exit_price', 'total_days', 'created_at']

    def validate_trade(self, trade):
    
        """Ensure trade is completed before allowing Accuracy creation."""
        if trade.status != 'COMPLETED':
            raise serializers.ValidationError("Accuracy can only be added for completed trades.")
        return trade

    def create(self, validated_data):
        """Override create to efficiently set `total_days`."""
        trade = validated_data['trade']

        # Compute total days only on creation
        if trade.completed_at and trade.created_at:
            validated_data['total_days'] = (trade.completed_at - trade.created_at).days

        return super().create(validated_data)


class TradeSerializer(serializers.ModelSerializer):
    company_details = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        fields = ["id", "trade_type", "status","plan_type", "company_details"]  # Include other necessary trade fields

    def get_company_details(self, obj):
        return {
            "symbol": obj.company.trading_symbol,
            "name": obj.company.script_name,
            "exchange": obj.company.exchange,
            "type": obj.company.instrument_type
        }


class TradeSerializers(serializers.ModelSerializer):
    company_details = serializers.SerializerMethodField()
    trade_history = serializers.SerializerMethodField()  # Method serializer for TradeHistory
    analysis = serializers.SerializerMethodField()  # Method serializer for Analysis
    accuracy = serializers.SerializerMethodField()  
    insight = serializers.SerializerMethodField()  
    image = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        fields = ['id', "company_details", 'trade_type', 'plan_type', 'warzone', 'warzone_history', 'is_free_call',
                  'image', 'created_at', 'updated_at', 'completed_at', 'trade_history', 'analysis', 'accuracy', 'insight']
    
    def get_image(self, obj):
        return obj.image.url if obj.image else None
    
    def get_company_details(self, obj):
        return {
            "symbol": obj.company.trading_symbol,
            "name": obj.company.script_name,
            "exchange": obj.company.exchange,
            "type": obj.company.instrument_type
        }

    def get_trade_history(self, obj):
        """Retrieve related trade history details"""
        trade_history_data = obj.history.all()  # Fetch related TradeHistory records
        return [
            {
                "buy": history.buy,
                "target": history.target,
                "sl": history.sl,
                "timestamp": history.timestamp,
                "updated_at": history.updated_at
            }
            for history in trade_history_data
        ]

    def get_analysis(self, obj):
        """Retrieve related analysis details"""
        if hasattr(obj, 'analysis'):  # Check if analysis exists
            return {
                "bull_scenario": obj.analysis.bull_scenario,
                "bear_scenario": obj.analysis.bear_scenario,
                "status": obj.analysis.status,
                "completed_at": obj.analysis.completed_at
            }
        return None  # Return None if no analysis record exists

    def get_accuracy(self, obj):
        """Retrieve accuracy details related to the trade"""
        accuracy_instance = obj.accuracy.first()  # Fetch the first related accuracy record if available
        if accuracy_instance:
            return {
                "target_hit": accuracy_instance.target_hit,
                "exit_price": accuracy_instance.exit_price,
                "total_days": accuracy_instance.total_days,
                "created_at": accuracy_instance.created_at,
                "updated_at": accuracy_instance.updated_at
            }
        return None  # Return None if no accuracy record exists

    def get_insight(self, obj):
        """Retrieve insight details related to the trade"""
        if hasattr(obj, 'insight'):  # Check if the related Insight exists
            return {
                "prediction_image": obj.insight.prediction_image.url if obj.insight.prediction_image else None,
                "actual_image": obj.insight.actual_image.url if obj.insight.actual_image else None,
                "prediction_description": obj.insight.prediction_description,
                "actual_description": obj.insight.actual_description,
                "accuracy_score": obj.insight.accuracy_score,
                "analysis_result": obj.insight.analysis_result,
                "created_at": obj.insight.created_at,
                "updated_at": obj.insight.updated_at
            }
        return None  # Return None if no insight record exists


# class TradeSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Trade
#         fields = ["id", "company", "user", "trade_type", "status", "plan_type", "created_at", "updated_at", "completed_at"]

# class AccuracyStatsSerializer(serializers.Serializer):
#     average_trade_duration = serializers.FloatField()
#     total_trades = serializers.IntegerField()
#     success_rate = serializers.FloatField()
#     active_trades_last_30_days = serializers.IntegerField()
#     total_completed_trades = serializers.IntegerField()