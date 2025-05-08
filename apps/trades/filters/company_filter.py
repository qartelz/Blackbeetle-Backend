from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters import rest_framework as filters
from django.db.models import Q
from ..models import Company, InstrumentType

class CompanyFilter(filters.FilterSet):
    search = filters.CharFilter(method='search_filter')
    instrument_type = filters.ChoiceFilter(choices=InstrumentType.choices)
    is_active = filters.BooleanFilter()
    expiry_date_from = filters.DateFilter(field_name='expiry_date', lookup_expr='gte')
    expiry_date_to = filters.DateFilter(field_name='expiry_date', lookup_expr='lte')
    # commodity = filters.CharFilter(field_name='trading_symbol', lookup_expr='icontains')
    exchange = filters.CharFilter(field_name='exchange', lookup_expr='iexact')

    class Meta:
        model = Company
        fields = ['exchange', 'instrument_type', 'is_active']

    def search_filter(self, queryset, name, value):
        return queryset.filter(
            Q(trading_symbol__icontains=value) |
            Q(script_name__icontains=value) |
            Q(display_name__icontains=value) |
            Q(exchange__icontains=value)
        )