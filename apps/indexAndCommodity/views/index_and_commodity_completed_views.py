from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count
from collections import defaultdict
from django.shortcuts import get_object_or_404
from  django.db.models.functions import TruncMonth

from rest_framework.pagination import PageNumberPagination
from collections import OrderedDict

from ..models import Trade
from ..serializers.completed_index_and_commodity_serializer import TradeListItemSerializer, TradeDetailSerializer

class MonthlyTradePagination(PageNumberPagination):
    page_size = 1  # One month per page
    page_size_query_param = 'page_size'
    max_page_size = 12  # Maximum 12 months

    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('total_pages', self.page.paginator.num_pages),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('current_page', self.page.number),
            ('results', data)
        ]))

class IndexAndCommodityCompletedViewSet(viewsets.ViewSet):
    pagination_class = MonthlyTradePagination

    @property
    def paginator(self):
        if not hasattr(self, '_paginator'):
            self._paginator = self.pagination_class()
        return self._paginator

    def list(self, request):
        """
        Get completed trades grouped by month with pagination
        """
        try:
            # Get completed trades with necessary related fields
            trades_query = Trade.objects.filter(
                status=Trade.Status.COMPLETED,
                completed_at__isnull=False
            ).select_related(
                'index_and_commodity',
                'index_and_commodity_analysis'
            ).prefetch_related(
                'index_and_commodity_history'
            ).annotate(
                month=TruncMonth('completed_at')
            ).order_by('-completed_at')

            # Group trades by month
            monthly_trades = defaultdict(list)
            for trade in trades_query:
                monthly_trades[trade.month].append(trade)

            # Convert to list of monthly data
            monthly_data = [
                {
                    'month': month,
                    'total_trades': len(trades),
                    'trades': TradeListItemSerializer(trades, many=True).data
                }
                for month, trades in sorted(monthly_trades.items(), key=lambda x: x[0], reverse=True)
            ]

            # Paginate results
            page = self.paginator.paginate_queryset(monthly_data, request)
            return self.paginator.get_paginated_response(page)

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def retrieve(self, request, pk=None):
        """
        Get detailed trade information
        """
        try:
            trade = get_object_or_404(
                Trade.objects.select_related(
                    'index_and_commodity',
                    'index_and_commodity_analysis',
                    'index_and_commodity_insight'
                ).prefetch_related(
                    'index_and_commodity_history'
                ),
                pk=pk
            )

            serializer = TradeDetailSerializer(trade, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
