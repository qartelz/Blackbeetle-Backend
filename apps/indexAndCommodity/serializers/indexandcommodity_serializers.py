from rest_framework import serializers
from ..models import IndexAndCommodity

class IndexAndCommoditySerializer(serializers.ModelSerializer):
    tradingSymbol = serializers.CharField(required=True, error_messages={
        'required': 'Trading symbol is required.',
        'blank': 'Trading symbol cannot be blank.'
    })
    exchange = serializers.CharField(required=True, error_messages={
        'required': 'Exchange is required.',
        'blank': 'Exchange cannot be blank.'
    })
    is_active = serializers.BooleanField(required=False, default=True)
    instrumentName = serializers.CharField(required=True, error_messages={
        'required': 'Instrument name is required.',
        'blank': 'Instrument name cannot be blank.'
    })

    class Meta:
        model = IndexAndCommodity
        fields = ['id', 'tradingSymbol', 'exchange', 'instrumentName', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['created_at', 'updated_at']

    def validate_tradingSymbol(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Trading symbol cannot be empty.")
        return value.strip()

    def validate_exchange(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Exchange cannot be empty.")
        return value.strip()

    def validate_instrumentName(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Instrument name cannot be empty.")
        return value.strip() 