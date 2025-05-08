from django.db.models import Q
from django_filters import rest_framework as filters
from ..models import Company, InstrumentType

class GroupedTradeFilter(filters.FilterSet):
    search = filters.CharFilter(method='search_filter')
    instrument_type = filters.ChoiceFilter(
        choices=[('index', 'Index'), ('stock', 'Stock'), ('commodity', 'Commodity')],
        method='filter_by_instrument'
    )
    exchange = filters.CharFilter(lookup_expr='iexact')
    status = filters.CharFilter(method='status_filter')
    tradingSymbol = filters.CharFilter(field_name='trading_symbol', lookup_expr='icontains')

    def filter_by_instrument(self, queryset, name, value):
        if value == 'index':
            return queryset.filter(Q(trading_symbol__icontains='NIFTY') | Q(trading_symbol__icontains='BANKNIFTY'))
        elif value == 'stock':
            return queryset.filter(instrument_type=InstrumentType.EQUITY)
        # elif value == 'commodity':
        #     return queryset.filter(instrument_type=InstrumentType.COMMODITY)
        return queryset
    def search_filter(self, queryset, name, value):
        return queryset.filter(
            Q(trading_symbol__icontains=value) |
            Q(script_name__icontains=value) |
            Q(display_name__icontains=value)
        )
    
    def status_filter(self, queryset, name, value):
        return queryset.filter(trades__status=value)

    class Meta:
        model = Company
        fields = ['exchange', 'instrument_type','tradingSymbol']

