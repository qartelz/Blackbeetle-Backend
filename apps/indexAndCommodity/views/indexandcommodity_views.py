from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from ..models import IndexAndCommodity
from ..serializers.indexandcommodity_serializers import IndexAndCommoditySerializer
from ..Filter.indexandcommodity_filter import IndexAndCommodityFilter

class IndexAndCommodityViewSet(viewsets.ModelViewSet):
    queryset = IndexAndCommodity.objects.all()
    serializer_class = IndexAndCommoditySerializer
    filterset_class = IndexAndCommodityFilter
    filter_backends = [DjangoFilterBackend]
    # permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        search_query = self.request.query_params.get('search', None)
        
        if search_query:
            queryset = queryset.filter(
                Q(tradingSymbol__icontains=search_query) | 
                Q(exchange__icontains=search_query) | 
                Q(instrumentName__icontains=search_query)
            )
        
        return queryset

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=kwargs.pop('partial', False))
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['GET'], url_path='active')
    def active_indices(self, request):
        active_queryset = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(active_queryset, many=True)
        return Response(data=serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['PATCH'], url_path='soft-delete')
    def soft_delete(self, request, pk=None):
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(data=serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['PATCH'], url_path='restore')
    def restore(self, request, pk=None):
        instance = self.get_object()
        instance.is_active = True
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(data=serializer.data, status=status.HTTP_200_OK)
