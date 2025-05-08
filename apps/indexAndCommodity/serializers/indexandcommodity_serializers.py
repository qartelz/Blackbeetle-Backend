from rest_framework import serializers
from ..models import IndexAndCommodity

class IndexAndCommoditySerializer(serializers.ModelSerializer):
    tradingSymbol = serializers.CharField(required=True)
    exchange = serializers.CharField(required=True)
    is_active = serializers.BooleanField(required=False)
    instrumentName = serializers.CharField(required=True)

    class Meta:
        model = IndexAndCommodity
        fields = ['id', 'tradingSymbol', 'exchange', 'instrumentName', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['created_at', 'updated_at'] 