import logging
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from ..models import Insight, Trade
from ..serializers.insight_serializers import InsightSerializer

logger = logging.getLogger(__name__)

class InsightViewSet(viewsets.ModelViewSet):
    queryset = Insight.objects.all()
    serializer_class = InsightSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        trade_id = self.request.query_params.get('trade_id', None)
        if trade_id is not None:
            queryset = queryset.filter(trade_id=trade_id)
        return queryset

    @action(detail=True, methods=['get'])
    def preview_image(self, request, pk=None):
        try:
            insight = self.get_object()
            if insight.prediction_image:
                return Response({'prediction_image_url': insight.prediction_image.url})
            if insight.actual_image:
                return Response({'actual_image_url': insight.actual_image.url})
            return Response({'error': 'No images available'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in preview_image: {str(e)}")
            print(e,'error---->>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>')
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        try:
            trade_id = request.data.get('trade')
            try:
                trade = Trade.objects.get(id=trade_id)
            except Trade.DoesNotExist:
                return Response({'error': 'Trade not found'}, status=status.HTTP_404_NOT_FOUND)

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(trade=trade)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except Exception as e:
            logger.error(f"Error in create: {str(e)}")
            print(e,'error------------------------------------->')
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, *args, **kwargs):
        try:
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error in update: {str(e)}")
            print(e,'error')
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
