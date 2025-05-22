from rest_framework import viewsets, status
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from ..models import IndexAndCommodity
from ..serializers.indexandcommodity_serializers import IndexAndCommoditySerializer
from ..Filter.indexandcommodity_filter import IndexAndCommodityFilter

class IndexAndCommodityViewSet(viewsets.ModelViewSet):
    queryset = IndexAndCommodity.objects.all()
    serializer_class = IndexAndCommoditySerializer
    filterset_class = IndexAndCommodityFilter
    filter_backends = [DjangoFilterBackend]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
<<<<<<< Updated upstream
        search_query = self.request.query_params.get('search', None)
        
        if search_query:
            queryset = queryset.filter(
                Q(tradingSymbol__icontains=search_query) | 
                Q(exchange__icontains=search_query) | 
                Q(instrumentName__icontains=search_query)
            )
        
=======
>>>>>>> Stashed changes
        return queryset

    def create(self, request, *args, **kwargs):
        try:
<<<<<<< Updated upstream
            # Log request data for debugging
            print("Request data:", request.data)
            
            # Validate required fields
            required_fields = ['tradingSymbol', 'exchange', 'instrumentName']
            for field in required_fields:
                if field not in request.data:
                    return Response(
                        {"error": f"{field} is required"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            serializer = self.get_serializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {"error": "Validation failed", "detail": serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )

            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except ValidationError as e:
            return Response(
                {"error": str(e), "detail": e.detail if hasattr(e, 'detail') else None},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            print("Error creating index and commodity:", str(e))  # Debug log
            return Response(
                {"error": "Failed to create index and commodity", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except ValidationError as e:
            return Response(
                {"error": str(e), "detail": e.detail if hasattr(e, 'detail') else None},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"error": "Failed to update index and commodity", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

=======
            # Remove editable=False fields from validation
            mutable_data = request.data.copy()
            serializer = self.get_serializer(data=mutable_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data, 
                status=status.HTTP_201_CREATED, 
                headers=headers
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def perform_create(self, serializer):
        # Allow saving despite editable=False fields
        instance = IndexAndCommodity(
            tradingSymbol=serializer.validated_data['tradingSymbol'],
            exchange=serializer.validated_data['exchange'],
            instrumentName=serializer.validated_data['instrumentName']
        )
        instance.save(force_insert=True)

>>>>>>> Stashed changes
    @action(detail=False, methods=['GET'], url_path='active')
    def active_indices(self, request):
        try:
            active_queryset = self.get_queryset().filter(is_active=True)
            serializer = self.get_serializer(active_queryset, many=True)
            return Response(data=serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": "Failed to fetch active indices", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['PATCH'], url_path='soft-delete')
    def soft_delete(self, request, pk=None):
        try:
            instance = self.get_object()
            instance.is_active = False
            instance.save()
            serializer = self.get_serializer(instance)
            return Response(data=serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": "Failed to soft delete index", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['PATCH'], url_path='restore')
    def restore(self, request, pk=None):
        try:
            instance = self.get_object()
            instance.is_active = True
            instance.save()
            serializer = self.get_serializer(instance)
            return Response(data=serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": "Failed to restore index", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
