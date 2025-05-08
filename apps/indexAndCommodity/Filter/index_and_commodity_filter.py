from django_filters import rest_framework as filters
from django.db.models import Q
from ..models import Trade, IndexAndCommodity

class TradeFilter(filters.FilterSet):
    search = filters.CharFilter(method='search_filter')
    status = filters.ChoiceFilter(choices=Trade.Status.choices)
    trade_type = filters.ChoiceFilter(choices=Trade.TradeType.choices)
    plan_type = filters.ChoiceFilter(choices=Trade.PlanType.choices)
    created_from = filters.DateFilter(field_name='created_at', lookup_expr='gte')
    created_to = filters.DateFilter(field_name='created_at', lookup_expr='lte')
    index_symbol = filters.CharFilter(field_name='index_and_commodity__tradingSymbol', lookup_expr='icontains')
    exchange = filters.CharFilter(field_name='index_and_commodity__exchange', lookup_expr='iexact')

    class Meta:
        model = Trade
        fields = ['status', 'trade_type', 'plan_type']

    def search_filter(self, queryset, name, value):
        return queryset.filter(
            Q(index_and_commodity__tradingSymbol__icontains=value) 
        )