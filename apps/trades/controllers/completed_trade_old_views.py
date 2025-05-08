# from rest_framework import viewsets
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.response import Response
# from rest_framework.exceptions import PermissionDenied
# from django_filters import rest_framework as filters
# from collections import defaultdict

# from ..models import Trade, Company
# from ..pagination import TradePagination

# from ..filters.GroupedTradeFilter import GroupedTradeFilter
# from ..serializers.complete_trade_old_serializer import CompletedTradeSerializer

# from django.utils import timezone
# from rest_framework import viewsets
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.exceptions import PermissionDenied
# from django_filters import rest_framework as filters
# from django.db.models import Q
# from django.utils import timezone

# class CompletedTradeViewSet(viewsets.ReadOnlyModelViewSet):
#     queryset = Company.objects.filter(trades__isnull=False,trades__status='COMPLETED').distinct()
#     serializer_class = CompletedTradeSerializer
#     filterset_class = GroupedTradeFilter
#     filter_backends = (filters.DjangoFilterBackend,)
#     pagination_class = TradePagination
    
   



from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters import rest_framework as filters
from collections import defaultdict

from ..models import Trade, Company
from ..pagination import TradePagination

from ..filters.GroupedTradeFilter import GroupedTradeFilter
from ..serializers.complete_trade_old_serializer import TradeListItemSerializer

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django_filters import rest_framework as filters
from django.db.models import Q
from django.utils import timezone

# class CompletedTradeViewSet(viewsets.ReadOnlyModelViewSet):
#     queryset = Trade.objects.all()
#     serializer_class = TradeListItemSerializer
#     # filterset_class = GroupedTradeFilter
#     filter_backends = (filters.DjangoFilterBackend,)
#     pagination_class = TradePagination

#     def get_queryset(self):
#         return Trade.objects.filter(status='COMPLETED').select_related('company','analysis','insight').prefetch_related('history')
    
    
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters import rest_framework as filters
from django.db.models import Q

from ..models import Trade, Company
from rest_framework import pagination
from ..serializers.complete_trade_old_serializer import TradeListItemSerializer
class TradePaginations(pagination.PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })

class CompletedTradeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Trade.objects.all()
    serializer_class = TradeListItemSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    pagination_class = TradePagination

    def get_queryset(self):
        return Trade.objects.filter(status='COMPLETED').select_related('company', 'analysis', 'insight').prefetch_related('history')
    
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
