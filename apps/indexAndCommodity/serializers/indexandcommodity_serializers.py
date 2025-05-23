from rest_framework import serializers
from ..models import IndexAndCommodity

class IndexAndCommoditySerializer(serializers.ModelSerializer):
    tradingSymbol = serializers.CharField(required=True)
    exchange = serializers.CharField(required=True)
    is_active = serializers.BooleanField(required=False)
    instrumentName = serializers.CharField(required=True)

    class Meta:
        model = IndexAndCommodity
        fields = [
            'id',
            'tradingSymbol',
            'exchange',
            'instrumentName',
            'created_at',
            'updated_at',
            'is_active'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, data):
        """
        Validate unique constraint for tradingSymbol, exchange, and instrumentName
        """
        tradingSymbol = data.get('tradingSymbol')
        exchange = data.get('exchange')
        instrumentName = data.get('instrumentName')

        # Check if instance exists with same values
        if self.instance is None:  # Creating new instance
            exists = IndexAndCommodity.objects.filter(
                tradingSymbol=tradingSymbol,
                exchange=exchange,
                instrumentName=instrumentName
            ).exists()
            if exists:
                raise serializers.ValidationError(
                    "Index with this trading symbol, exchange and instrument type already exists"
                )
        
        return data 