from rest_framework import viewsets, status
from rest_framework.response import Response 
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction
from django_filters import rest_framework as filters
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.db.models import Q
from ..models import Trade, Analysis
from ..serializers.trade_serializers import (
    TradeSerializer, 
    TradeListSerializer,
    TradeCreateSerializer,
    TradeUpdateSerializer,
    AnalysisSerializer,
)
from ..filters.TradeFilter import TradeFilter
from ..pagination import TradePagination
import logging

logger = logging.getLogger(__name__)

class TradeViewSet(viewsets.ModelViewSet):
    queryset = Trade.objects.all()
    serializer_class = TradeSerializer
    filterset_class = TradeFilter
    filter_backends = (filters.DjangoFilterBackend,)
    pagination_class = TradePagination
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return TradeListSerializer
        elif self.action == 'create':
            return TradeCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return TradeUpdateSerializer
        return TradeSerializer

    def get_queryset(self):
        user = self.request.user
        current_date = timezone.now().date()
        
        queryset = super().get_queryset()
        
        if user.is_staff:
            return queryset.filter(status__in=['PENDING', 'ACTIVE', 'COMPLETED']).exclude(status= 'CANCELLED').order_by('-created_at')
        
        # Get active subscription
        current_subscription = user.subscriptions.filter(
            is_active=True,
            start_date__lte=current_date,
            end_date__gte=current_date
        ).first()
        
        # If no active subscription, return free calls only
        if not current_subscription:
            return queryset.filter(is_free_call=True).order_by('-created_at')
        
        plan_type = current_subscription.plan.name
        base_query = queryset.filter(
            created_at__date__gte=current_subscription.start_date,
            created_at__date__lte=current_subscription.end_date
        )
        
        plan_filters = {
            'BASIC': ['BASIC'],
            'PREMIUM': ['BASIC', 'PREMIUM'],
            'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
        }
        
        allowed_plans = plan_filters.get(plan_type, [])
        return base_query.filter(
            Q(plan_type__in=allowed_plans) | Q(is_free_call=True)
        ).order_by('-created_at')

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create trade with analysis"""
        try:
            # First validate the data
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            # Create the trade
            trade = serializer.save(user=request.user)
            
            # Create initial notification if needed
            try:
                from ..models import TradeNotification
                TradeNotification.create_trade_notification(
                    user=request.user,
                    trade=trade,
                    notification_type=TradeNotification.NotificationType.TRADE_ACTIVATED,
                    message=f"New {trade.trade_type.lower()} trade created for {trade.company.trading_symbol}",
                    priority=TradeNotification.Priority.HIGH
                )
            except Exception as e:
                logger.error(f"Error creating initial notification: {str(e)}")
                # Don't raise the error - we still want to return the created trade
            
            return Response(
                TradeSerializer(trade).data,
                status=status.HTTP_201_CREATED
            )
            
        except DjangoValidationError as e:
            logger.error(f"Django validation error: {str(e)}")
            return Response(
                {'error': e.messages if hasattr(e, 'messages') else [str(e)]},
                status=status.HTTP_400_BAD_REQUEST
            )
        except DRFValidationError as e:
            logger.error(f"DRF validation error: {str(e)}")
            return Response(
                {'error': e.detail if hasattr(e, 'detail') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error creating trade: {str(e)}")
            return Response(
                {'error': f'An unexpected error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial
        )
        serializer.is_valid(raise_exception=True)
        
        # If `image` is in request.FILES, handle it via the serializer
        if 'image' in request.FILES:
            request.data['image'] = request.FILES['image']
        
        try:
            trade = serializer.save()
            return Response(TradeSerializer(trade).data)
        except DjangoValidationError as e:
            return Response(
                {'error': e.messages},  # Extract messages from the exception
                status=status.HTTP_400_BAD_REQUEST
            )
        except DRFValidationError as e:
            return Response(
                {'error': e.detail},
                status=status.HTTP_400_BAD_REQUEST
            )

    def destroy(self, request, *args, **kwargs):
        """Soft delete"""
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['PATCH'])
    def update_analysis(self, request, pk=None):
        """Update trade analysis"""
        trade = self.get_object()
        
        if not hasattr(trade, 'analysis'):
            return Response(
                {'error': 'No analysis exists for this trade'},
                status=status.HTTP_404_NOT_FOUND
            )
            
        analysis_serializer = AnalysisSerializer(
            trade.analysis,
            data=request.data,
            partial=True
        )
        analysis_serializer.is_valid(raise_exception=True)
        try:
            analysis = analysis_serializer.save()
            return Response(AnalysisSerializer(analysis).data)
        except DjangoValidationError as e:
            return Response(
                {'error': e.messages if hasattr(e, 'messages') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except DRFValidationError as e:
            return Response(
                {'error': e.detail if hasattr(e, 'detail') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            # For unexpected errors, return a more generic message
            return Response(
                {'error': f'An unexpected error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )