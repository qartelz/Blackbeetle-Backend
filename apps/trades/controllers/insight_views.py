from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, DatabaseError
from ..models import Insight, Trade
from ..serializers.insight_serializers import InsightSerializer, InsightCreateUpdateSerializer

class InsightViewSet(viewsets.ModelViewSet):
    queryset = Insight.objects.all()
    serializer_class = InsightSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return InsightCreateUpdateSerializer
        return InsightSerializer

    def create(self, request, *args, **kwargs):
        try:
            trade_id = request.data.get('trade')
            if not trade_id:
                return Response(
                    {"error": "Trade ID is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            try:
                trade = get_object_or_404(Trade, id=trade_id)
            except ObjectDoesNotExist:
                return Response(
                    {"error": f"Trade with id {trade_id} does not exist."},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            if trade.status != Trade.Status.COMPLETED:
                return Response(
                    {"error": "Insights can only be created for completed trades."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(trade=trade)
            
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
            
        except IntegrityError as e:
            return Response(
                {"error": f"Database integrity error: {str(e)}"},
                status=status.HTTP_409_CONFLICT
            )
        except DatabaseError as e:
            return Response(
                {"error": f"Database error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            return Response(
                {"error": f"An unexpected error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['GET'])
    def for_trade(self, request, pk=None):
        try:
            try:
                trade = get_object_or_404(Trade, id=pk)
            except ObjectDoesNotExist:
                return Response(
                    {"error": f"Trade with id {pk} does not exist."},
                    status=status.HTTP_404_NOT_FOUND
                )
                
            try:
                insight = get_object_or_404(Insight, trade=trade)
            except ObjectDoesNotExist:
                return Response(
                    {"error": f"No insight found for trade with id {pk}."},
                    status=status.HTTP_404_NOT_FOUND
                )
                
            serializer = self.get_serializer(insight)
            return Response(serializer.data)
            
        except DatabaseError as e:
            return Response(
                {"error": f"Database error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            return Response(
                {"error": f"An unexpected error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )