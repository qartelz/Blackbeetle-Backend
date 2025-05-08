from rest_framework import serializers
from ..models import TradeHistory

class TradeHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeHistory
        fields = ['id', 'trade', 'buy', 'target', 'sl', 'timestamp', 'updated_at', 'risk_reward_ratio', 'potential_profit_percentage', 'stop_loss_percentage']
        read_only_fields = ['timestamp', 'updated_at']

    # def validate(self, data):
    #     if data['target'] <= data['buy']:
    #         raise serializers.ValidationError("Target must be higher than the buy price.")
        
    #     if data['sl'] >= data['buy']:
    #         raise serializers.ValidationError("Stop loss must be lower than the buy price.")
        
    #     return data

