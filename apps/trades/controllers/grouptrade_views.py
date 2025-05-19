from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters import rest_framework as filters
from collections import defaultdict

from ..models import Trade, Company
from ..pagination import TradePagination

from ..filters.GroupedTradeFilter import GroupedTradeFilter
from ..serializers.GroupedTradeSerializer import GroupedTradeSerializer

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django_filters import rest_framework as filters
from django.db.models import Q

class GroupedTradeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Company.objects.filter(trades__isnull=False).distinct()
    serializer_class = GroupedTradeSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = GroupedTradeFilter
    filter_backends = (filters.DjangoFilterBackend,)
    pagination_class = TradePagination
    
    def get_queryset(self):
        user = self.request.user
        current_datetime = timezone.now()  # Use datetime instead of date
        
        base_queryset = super().get_queryset()
        
        if user.is_staff:
            return base_queryset
            
        # Get active subscription using datetime comparisons
        current_subscription = user.subscriptions.filter(
            is_active=True,
            start_date__lte=current_datetime,
            end_date__gte=current_datetime
        ).first()
        
        # Handle users with no subscription
        if not current_subscription:
            free_trades = base_queryset.filter(trades__is_free_call=True)
            if not free_trades.exists():
                raise PermissionDenied(
                    detail="You don't have an active subscription plan. "
                    "Please subscribe to access trade information."
                )
            return free_trades

        # Process based on subscription plan
        plan_type = current_subscription.plan.name
        plan_filters = {
            'BASIC': ['BASIC'],
            'PREMIUM': ['BASIC', 'PREMIUM'],
            'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM'],
            'FREE_TRIAL': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']  # Added FREE_TRIAL type
        }
        
        allowed_plans = plan_filters.get(plan_type, [])
        
        filtered_queryset = base_queryset.filter(
            trades__status__in=['ACTIVE', 'COMPLETED']
        ).filter(
            Q(trades__plan_type__in=allowed_plans) |
            Q(trades__is_free_call=True)
        ).distinct()
        
        return filtered_queryset