from rest_framework import viewsets, status
from rest_framework.response import Response
from ..models import TradeHistory, Trade
from ..serializers.trade_history_serializer import TradeHistorySerializer

from rest_framework.decorators import action
from django_filters import rest_framework as filters

class TradeHistoryFilter(filters.FilterSet):
    trade_id = filters.NumberFilter(field_name='trade__id')
    
    class Meta:
        model = TradeHistory
        fields = ['trade_id']

class TradeHistoryViewSet(viewsets.ModelViewSet):
    queryset = TradeHistory.objects.all()
    serializer_class = TradeHistorySerializer
    filterset_class = TradeHistoryFilter

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

    @action(detail=False, methods=['GET'], url_path='trade/(?P<trade_id>[^/.]+)/history')
    def trade_history(self, request, trade_id=None):
        try:
            trade = Trade.objects.get(id=trade_id)
        except Trade.DoesNotExist:
            return Response(
                {'error': 'Trade not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        trade_history = TradeHistory.objects.filter(trade=trade).order_by('-timestamp')
        serializer = self.get_serializer(trade_history, many=True)
        
        return Response(serializer.data, status=status.HTTP_200_OK)

