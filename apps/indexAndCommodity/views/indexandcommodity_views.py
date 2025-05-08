from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

from ..models import IndexAndCommodity
from ..serializers.indexandcommodity_serializers import IndexAndCommoditySerializer
from ..Filter.indexandcommodity_filter import IndexAndCommodityFilter

class IndexAndCommodityViewSet(viewsets.ModelViewSet):
    queryset = IndexAndCommodity.objects.all()
    serializer_class = IndexAndCommoditySerializer
    filterset_class = IndexAndCommodityFilter
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        queryset = super().get_queryset()
        # search_query = self.request.query_params.get('search', None)
        
        # if search_query:
        #     queryset = queryset.filter(
        #         Q(tradingSymbol__icontains=search_query) | 
        #         Q(exchange__icontains=search_query) | 
        #         Q(instrumentName__icontains=search_query)
        #     )
        
        return queryset

    @action(detail=False, methods=['GET'], url_path='active')
    def active_indices(self, request):
        active_queryset = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(active_queryset, many=True)
        return Response(data=serializer.data,status=status.HTTP_200_OK)

    @action(detail=True, methods=['PATCH'], url_path='soft-delete')
    def soft_delete(self, request, pk=None):
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(data=serializer.data,status=status.HTTP_200_OK)

    @action(detail=True, methods=['PATCH'], url_path='restore')
    def restore(self, request, pk=None):
        instance = self.get_object()
        instance.is_active = True
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(data=serializer.data,status=status.HTTP_200_OK)
