from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters import rest_framework as filters
from django.db.models import Q
from collections import defaultdict

from ..models import Trade, IndexAndCommodity
# from ..Filter.GroupedTradeFilter import GroupedTradeFilter



from ..serializers.grouped_trades_serializers import IndexAndCommodityTradesSerializer

from django.utils import timezone


class GroupedTradeFilter(filters.FilterSet):
    status = filters.ChoiceFilter(
        choices=[('ACTIVE', 'Active')],
        method='filter_status'
    )
    instrumentName = filters.ChoiceFilter(
        choices=IndexAndCommodity.InstrumentType.choices
    )
    tradingSymbol = filters.CharFilter(field_name='tradingSymbol', lookup_expr='icontains')

    class Meta:
        model = IndexAndCommodity
        fields = ['status', 'instrumentName', 'tradingSymbol']
    
    def filter_status(self, queryset, name, value):
        if value:
            return queryset.filter(
                trades__status=value
            ).distinct()
        return queryset



class GroupedTradeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = IndexAndCommodityTradesSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = GroupedTradeFilter
    
    def get_queryset(self):
        user = self.request.user
        current_date = timezone.now().date()
        
        # Get indices that have active or completed trades
        base_queryset = IndexAndCommodity.objects.filter(
            trades__status__in=['ACTIVE']
        ).distinct()
        
        if user.is_staff:
            return base_queryset
            
        current_subscription = user.subscriptions.filter(
            is_active=True,
            start_date__lte=current_date,
            end_date__gte=current_date
        ).first()

        if not current_subscription:
            raise PermissionDenied(
                detail="You don't have an active subscription plan. "
                "Please subscribe to access trade information."
            )

        # Get trades within the subscription period and plan type
        plan_type = current_subscription.plan.name
        plan_filters = {
            'BASIC': ['BASIC'],
            'PREMIUM': ['BASIC', 'PREMIUM'],
            'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
        }
        
        allowed_plans = plan_filters.get(plan_type, [])
        
        return base_queryset.filter(
            trades__created_at__date__gte=current_subscription.start_date,
            trades__created_at__date__lte=current_subscription.end_date,
            trades__plan_type__in=allowed_plans
        ).distinct()