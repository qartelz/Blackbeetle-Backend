from rest_framework import viewsets, status
from rest_framework.response import Response
from ..models import TradeHistory
from ..serializers.trade_serializers import TradeHistorySerializer

class TradeHistoryViewSet(viewsets.ModelViewSet):
    serializer_class = TradeHistorySerializer
    
    def get_queryset(self):
        return TradeHistory.objects.filter(
            trade_id=self.kwargs['trade_pk']
        ).order_by('-timestamp')

    def create(self, request, *args, **kwargs):
        """Create new trade history entry"""
        trade_id = self.kwargs['trade_pk']
        
        # Get the initial buy price if it exists
        # initial_history = TradeHistory.objects.filter(trade_id=trade_id).first()
        # if initial_history:
        #     # For subsequent entries, use the initial buy price
        #     request.data['buy'] = initial_history.buy
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(trade_id=trade_id)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Update trade history entry"""
        instance = self.get_object()
        
        # Prevent updating buy price for any entry
        if 'buy' in request.data and request.data['buy'] != instance.buy:
            return Response(
                {'error': 'Buy price cannot be modified'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)