from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django_filters.rest_framework import DjangoFilterBackend
from ..models import FreeCallTrade
from ..serializers.freecall_serializer import (
    FreeCallTradeSerializer, 
    FreeCallTradeCreateSerializer, 
    FreeCallTradeUpdateSerializer
)
from ..pagination import StandardResultsSetPagination

class IsStaffUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_staff

    def has_object_permission(self, request, view, obj):
        if not request.user.is_staff:
            raise PermissionDenied(
                detail="Access denied. This action requires staff privileges. Please contact your administrator if you believe this is an error.",
                code=status.HTTP_403_FORBIDDEN
            )
        return True

class FreeCallTradeViewSet(viewsets.ModelViewSet):
    queryset = FreeCallTrade.objects.filter(is_deleted=False)
    serializer_class = FreeCallTradeSerializer
    permission_classes = [IsStaffUser]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'trade_type', 'sentiment']
    search_fields = ['company__trading_symbol', 'company__display_name']
    ordering_fields = ['created_at', 'updated_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return FreeCallTradeCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return FreeCallTradeUpdateSerializer
        return self.serializer_class

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(
                {
                    "message": "Trade call created successfully",
                    "data": serializer.data
                },
                status=status.HTTP_201_CREATED,
                headers=headers
            )
        except ValidationError as e:
            error_messages = []
            if hasattr(e.detail, 'items'):
                for field, errors in e.detail.items():
                    error_messages.append(f"{field}: {', '.join(map(str, errors))}")
            else:
                error_messages = [str(e)]
            
            return Response(
                {
                    "message": "Unable to create trade call",
                    "errors": error_messages,
                    "detail": "Please check the provided information and try again."
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except IntegrityError as e:
            return Response(
                {
                    "message": "Unable to create trade call",
                    "detail": "A trade call with these details already exists. Please modify your request and try again.",
                    "error": str(e)
                },
                status=status.HTTP_409_CONFLICT
            )
        except Exception as e:
            return Response(
                {
                    "message": "Server error occurred",
                    "detail": "An unexpected error occurred while creating the trade call. Please try again later or contact support if the problem persists."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        try:
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            serializer = self.get_serializer(
                instance,
                data=request.data,
                partial=partial
            )
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(
                {
                    "message": "Trade call updated successfully",
                    "data": serializer.data
                },
                status=status.HTTP_200_OK
            )
        except ObjectDoesNotExist:
            return Response(
                {
                    "message": "Trade not found",
                    "detail": "The requested trade call does not exist or has been deleted."
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except ValidationError as e:
            error_messages = []
            if hasattr(e.detail, 'items'):
                for field, errors in e.detail.items():
                    error_messages.append(f"{field}: {', '.join(map(str, errors))}")
            else:
                error_messages = [str(e)]
            
            return Response(
                {
                    "message": "Unable to update trade call",
                    "errors": error_messages,
                    "detail": "Please check the provided information and try again."
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    "message": "Server error occurred",
                    "detail": "An unexpected error occurred while updating the trade call. Please try again later or contact support if the problem persists."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response(
                {
                    "message": "Trade call deleted successfully",
                    "detail": "The trade call has been permanently removed from the system."
                },
                status=status.HTTP_204_NO_CONTENT
            )
        except ObjectDoesNotExist:
            return Response(
                {
                    "message": "Trade not found",
                    "detail": "The trade call you're trying to delete does not exist or has already been removed."
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {
                    "message": "Server error occurred",
                    "detail": "An unexpected error occurred while deleting the trade call. Please try again later or contact support if the problem persists."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def perform_create(self, serializer):
        try:
            serializer.save(created_by=self.request.user)
        except ValidationError as e:
            raise ValidationError(
                detail={
                    "message": "Validation failed",
                    "errors": str(e)
                }
            )

    @action(detail=True, methods=['post'])
    def soft_delete(self, request, pk=None):
        try:
            free_call_trade = self.get_object()
            free_call_trade.is_deleted = True
            free_call_trade.save()
            return Response(
                {
                    "message": "Trade call archived successfully",
                    "detail": "The trade call has been archived and will no longer appear in the active listings."
                },
                status=status.HTTP_200_OK
            )
        except ObjectDoesNotExist:
            return Response(
                {
                    "message": "Trade not found",
                    "detail": "The trade call you're trying to archive does not exist or has already been removed."
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {
                    "message": "Server error occurred",
                    "detail": "An unexpected error occurred while archiving the trade call. Please try again later or contact support if the problem persists."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PublicFreeCallTradeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FreeCallTradeSerializer
    # permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return FreeCallTrade.objects.filter(
            is_deleted=False,
            status='ACTIVE'
        ).order_by('-created_at')[:2]

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            if not queryset.exists():
                return Response(
                    {
                        "message": "No active trades found",
                        "detail": "There are currently no active trade calls available."
                    },
                    status=status.HTTP_204_NO_CONTENT
                )
            serializer = self.get_serializer(queryset, many=True)
            return Response(
                {
                    "message": "Active trades retrieved successfully",
                    "data": serializer.data
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "message": "Server error occurred",
                    "detail": "An unexpected error occurred while fetching trade calls. Please try again later or contact support if the problem persists."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(
                {
                    "message": "Trade details retrieved successfully",
                    "data": serializer.data
                },
                status=status.HTTP_200_OK
            )
        except ObjectDoesNotExist:
            return Response(
                {
                    "message": "Trade not found",
                    "detail": "The requested trade call does not exist or has been removed."
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {
                    "message": "Server error occurred",
                    "detail": "An unexpected error occurred while fetching the trade call details. Please try again later or contact support if the problem persists."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )