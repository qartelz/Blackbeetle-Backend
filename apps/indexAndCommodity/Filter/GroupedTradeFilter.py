# filters.py
from django_filters import rest_framework as filters
from ..models import IndexAndCommodity, Trade

class GroupedTradeFilter(filters.FilterSet):
    status = filters.ChoiceFilter(
        choices=[('ACTIVE', 'Active'), ('COMPLETED', 'Completed')],
        method='filter_status'
    )
    instrumentName = filters.ChoiceFilter(
        choices=IndexAndCommodity.InstrumentType.choices
    )
    tradingSymbol = filters.CharFilter(field_name='tradingSymbol', lookup_expr='icontains')

    class Meta:
        model = IndexAndCommodity
        fields = ['status', 'instrumentName', 'tradingSymbol']
    
    def filter_status(self, queryset, name, value):
        if value:
            return queryset.filter(
                index_and_commodity_trades__status=value
            ).distinct()
        return queryset