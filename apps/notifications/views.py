from .serializers import NotificationSerializer
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Notification
from django.db.models import Q, OuterRef, Subquery
from apps.trades.models import Trade, Company
from apps.subscriptions.models import Subscription
import logging

logger = logging.getLogger(__name__)

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # If user is staff, return all their notifications
        if user.is_staff:
            base_queryset = Notification.objects.filter(
                recipient=user
            ).select_related('content_type')
            return base_queryset.order_by('-created_at')
        
        # Get the user's active subscription
        subscription = Subscription.objects.filter(
            user=user,
            is_active=True,
            end_date__gte=timezone.now()
        ).first()
        
        # Start with all notifications for this user
        base_queryset = Notification.objects.filter(
            recipient=user
        ).select_related('content_type')
        
        # If user has no subscription, only return non-trade notifications
        if not subscription:
            return base_queryset.filter(
                Q(trade_id__isnull=True) | 
                Q(trade_id__in=Trade.objects.filter(is_free_call=True).values_list('id', flat=True))
            ).order_by('-created_at')
        
        # For SUPER_PREMIUM and FREE_TRIAL - return all notifications
        if subscription.plan.name in ['SUPER_PREMIUM', 'FREE_TRIAL']:
            return base_queryset.order_by('-created_at')
        
        # For other subscriptions, get accessible trades based on plan type
        plan_type = subscription.plan.name
        subscription_date = subscription.start_date
        
        # Define allowed plan types based on subscription
        plan_filters = {
            'BASIC': ['BASIC'],
            'PREMIUM': ['BASIC', 'PREMIUM'],
        }
        allowed_plans = plan_filters.get(plan_type, [])
        
        # Get new trades (created after subscription)
        new_trades_limit = 6 if plan_type == 'BASIC' else 9
        new_trades = Trade.objects.filter(
            status__in=['ACTIVE', 'COMPLETED'],
            created_at__gte=subscription_date,
            plan_type__in=allowed_plans
        ).order_by('created_at')[:new_trades_limit]
        
        # Get previous trades (active at subscription start)
        previous_trades = Trade.objects.filter(
            status__in=['ACTIVE', 'COMPLETED'],
            created_at__lt=subscription_date,
            plan_type__in=allowed_plans
        ).order_by('-created_at')[:6]
        
        # Get IDs of accessible trades
        accessible_trade_ids = list(new_trades.values_list('id', flat=True)) + list(previous_trades.values_list('id', flat=True))
        
        # Add free trades
        free_trade_ids = Trade.objects.filter(is_free_call=True).values_list('id', flat=True)
        accessible_trade_ids.extend(free_trade_ids)
        
        # Filter notifications for accessible trades or non-trade notifications
        return base_queryset.filter(
            Q(trade_id__isnull=True) | 
            Q(trade_id__in=accessible_trade_ids)
        ).order_by('-created_at')
    
    def list(self, request, *args, **kwargs):
        # Filter based on read status if specified
        is_read = request.query_params.get('is_read')
        queryset = self.get_queryset()
        
        if is_read is not None:
            is_read = is_read.lower() == 'true'
            queryset = queryset.filter(is_read=is_read)
        
        # Add count of unread notifications in response
        unread_count = self.get_queryset().filter(is_read=False).count()
        
        # Get trade information for enhancing notifications
        trade_ids = [n.trade_id for n in queryset if n.trade_id]
        trade_info = {}
        
        if trade_ids:
            trades = Trade.objects.filter(id__in=trade_ids).select_related('company')
            trade_info = {
                t.id: {
                    'tradingSymbol': t.company.trading_symbol,
                    'instrumentName': t.company.instrument_type
                } for t in trades
            }
        
        # Paginate results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            
            # Enhance serialized data with trade information
            enhanced_data = self._enhance_notification_data(serializer.data, trade_info)
            
            response = self.get_paginated_response(enhanced_data)
            response.data['unread_count'] = unread_count
            return response
        
        serializer = self.get_serializer(queryset, many=True)
        
        # Enhance serialized data with trade information
        enhanced_data = self._enhance_notification_data(serializer.data, trade_info)
        
        return Response({
            'results': enhanced_data,
            'unread_count': unread_count
        })
    
    def _enhance_notification_data(self, data, trade_info):
        """Add trading symbol and instrument name to notification data"""
        enhanced_data = []
        
        for item in data:
            trade_id = item.get('trade_id')
            if trade_id and trade_id in trade_info:
                # Add trading symbol and instrument name
                item['tradingSymbol'] = trade_info[trade_id]['tradingSymbol']
                item['instrumentName'] = trade_info[trade_id]['instrumentName']
            
            enhanced_data.append(item)
            
        return enhanced_data
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a single notification as read"""
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        
        # Add trade info to response
        response_data = self.get_serializer(notification).data
        
        if notification.trade_id:
            try:
                trade = Trade.objects.select_related('company').get(id=notification.trade_id)
                response_data['tradingSymbol'] = trade.company.trading_symbol
                response_data['instrumentName'] = trade.company.instrument_type
            except Trade.DoesNotExist:
                pass
                
        return Response(response_data)
    
    @action(detail=True, methods=['post'])
    def mark_unread(self, request, pk=None):
        """Mark a single notification as unread"""
        notification = self.get_object()
        notification.is_read = False
        notification.save()
        
        # Add trade info to response
        response_data = self.get_serializer(notification).data
        
        if notification.trade_id:
            try:
                trade = Trade.objects.select_related('company').get(id=notification.trade_id)
                response_data['tradingSymbol'] = trade.company.trading_symbol
                response_data['instrumentName'] = trade.company.instrument_type
            except Trade.DoesNotExist:
                pass
                
        return Response(response_data)
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        # Optional: Filter by notification type
        notification_type = request.data.get('notification_type')
        # Optional: Filter by date range
        before_date = request.data.get('before_date')
        
        queryset = self.get_queryset().filter(is_read=False)
        
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)
        
        if before_date:
            queryset = queryset.filter(created_at__lte=before_date)
        
        updated_count = queryset.update(
            is_read=True,
            updated_at=timezone.now()
        )
        
        return Response({
            'status': 'success',
            'marked_read': updated_count
        })