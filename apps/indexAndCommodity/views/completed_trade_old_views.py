from rest_framework import viewsets
from django_filters import rest_framework as filters
from rest_framework.response import Response
from rest_framework import pagination
from django.db.models import Q
from ..serializers.complete_trade_old_serializer import TradeListItemSerializer
from ..models import Trade,IndexAndCommodity

class GroupedTradeFilter(filters.FilterSet):
    exchange = filters.CharFilter(field_name='index_and_commodity__exchange')
    instrumentName = filters.ChoiceFilter(field_name='index_and_commodity__instrumentName', choices=IndexAndCommodity.InstrumentType.choices)
    tradingSymbol = filters.CharFilter(field_name='index_and_commodity__tradingSymbol')

    class Meta:
        model = Trade
        fields = ['exchange', 'instrumentName', 'tradingSymbol']

class TradePagination(pagination.PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class CompletedTradeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Trade.objects.all()
    serializer_class = TradeListItemSerializer
    filterset_class = GroupedTradeFilter
    filter_backends = (filters.DjangoFilterBackend,)
    pagination_class = TradePagination

    def get_queryset(self):
        return Trade.objects.filter(status='COMPLETED').select_related('index_and_commodity', 'index_and_commodity_analysis', 'index_and_commodity_insight').prefetch_related('index_and_commodity_history')
    
    def retrieve(self, request, *args, **kwargs):
        """
        Override retrieve to return single object in paginated format
        """
        instance = self.get_object()
        
        # Create a queryset with just this instance
        queryset = Trade.objects.filter(pk=instance.pk)
        
        # Get paginated response
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
