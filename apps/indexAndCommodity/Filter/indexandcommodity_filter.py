import django_filters
from ..models import IndexAndCommodity
from django.db.models import Q

class IndexAndCommodityFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search')
    # trading_symbol = django_filters.CharFilter(field_name='tradingSymbol', lookup_expr='icontains')
    
    class Meta:
        model = IndexAndCommodity
        fields = ['tradingSymbol', 'exchange', 'instrumentName', 'is_active']
    
    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(tradingSymbol__icontains=value) | 
            Q(exchange__icontains=value) | 
            Q(instrumentName__icontains=value)
        )