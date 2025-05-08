from django_filters import rest_framework as filters
from ..models import Trade

class TradeFilter(filters.FilterSet):
    min_warzone = filters.NumberFilter(field_name='warzone', lookup_expr='gte')
    max_warzone = filters.NumberFilter(field_name='warzone', lookup_expr='lte')
    
    created_start = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_end = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    
    trading_symbol = filters.CharFilter(
        field_name='index_and_commodity__tradingSymbol', 
        lookup_expr='icontains'
    )
    
    trade_duration = filters.CharFilter(method='filter_trade_duration')
    
    class Meta:
        model = Trade
        fields = [
            'trade_type', 
            'status', 
            'plan_type', 
            'min_warzone', 
            'max_warzone',
            'created_start', 
            'created_end',
            'trading_symbol'
        ]
    
    def filter_trade_duration(self, queryset, name, value):
        if value == 'intraday':
            return queryset.filter(trade_type=Trade.TradeType.INTRADAY)
        elif value == 'positional':
            return queryset.filter(trade_type=Trade.TradeType.POSITIONAL)
        return queryset