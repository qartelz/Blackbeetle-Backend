"""this code is rajids code"""

# from .serializers import NotificationSerializer
# from rest_framework import viewsets, status
# from rest_framework.decorators import action
# from rest_framework.response import Response
# from rest_framework.permissions import IsAuthenticated
# from django.utils import timezone
# from .models import Notification

# class NotificationViewSet(viewsets.ModelViewSet):
#     serializer_class = NotificationSerializer
#     permission_classes = [IsAuthenticated]
    
#     def get_queryset(self):
#         return Notification.objects.filter(
#             recipient=self.request.user
#         ).select_related(
#             'content_type'
#         ).order_by('-created_at')
    
#     def list(self, request, *args, **kwargs):
#         # Filter based on read status if specified
#         is_read = request.query_params.get('is_read')
#         queryset = self.get_queryset()
        
#         if is_read is not None:
#             is_read = is_read.lower() == 'true'
#             queryset = queryset.filter(is_read=is_read)
        
#         # Add count of unread notifications in response
#         unread_count = self.get_queryset().filter(is_read=False).count()
        
#         # Paginate results
#         page = self.paginate_queryset(queryset)
#         if page is not None:
#             serializer = self.get_serializer(page, many=True)
#             response = self.get_paginated_response(serializer.data)
#             response.data['unread_count'] = unread_count
#             return response
        
#         serializer = self.get_serializer(queryset, many=True)
#         return Response({
#             'results': serializer.data,
#             'unread_count': unread_count
#         })
    
#     @action(detail=True, methods=['post'])
#     def mark_read(self, request, pk=None):
#         """Mark a single notification as read"""
#         notification = self.get_object()
#         notification.is_read = True
#         notification.save()
#         return Response(self.get_serializer(notification).data)
    
#     @action(detail=True, methods=['post'])
#     def mark_unread(self, request, pk=None):
#         """Mark a single notification as unread"""
#         notification = self.get_object()
#         notification.is_read = False
#         notification.save()
#         return Response(self.get_serializer(notification).data)
    
#     @action(detail=False, methods=['post'])
#     def mark_all_read(self, request):
#         """Mark all notifications as read"""
#         # Optional: Filter by notification type
#         notification_type = request.data.get('notification_type')
#         # Optional: Filter by date range
#         before_date = request.data.get('before_date')
        
#         queryset = self.get_queryset().filter(is_read=False)
        
#         if notification_type:
#             queryset = queryset.filter(notification_type=notification_type)
        
#         if before_date:
#             queryset = queryset.filter(created_at__lte=before_date)
        
#         updated_count = queryset.update(
#             is_read=True,
#             updated_at=timezone.now()
#         )
        
#         return Response({
#             'status': 'success',
#             'marked_read': updated_count
#         })



from .serializers import NotificationSerializer
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Q
from .models import Notification, TradeNotification
from apps.trades.models import Trade
from apps.subscriptions.models import Subscription
import logging

logger = logging.getLogger(__name__)

class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for handling user notifications with subscription-based access control.
    
    This ViewSet manages notifications for users based on their subscription level:
    - BASIC: Access to notifications for 6 previous + 6 new trades
    - PREMIUM: Access to notifications for 6 previous + 9 new trades
    - SUPER_PREMIUM: Access to all notifications
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Get notifications based on user's subscription and trade access.
        
        Returns:
            QuerySet: Filtered notifications based on:
            - User's subscription level
            - Trade accessibility
            - Notification type
            - Read status
        """
        try:
            # Get user's active subscription with plan details
            subscription = Subscription.objects.select_related('plan').filter(
                user=self.request.user,
                is_active=True,
                start_date__lte=timezone.now(),
                end_date__gte=timezone.now()
            ).first()

            if not subscription:
                logger.warning(f"No active subscription found for user {self.request.user.id}")
                return Notification.objects.none()

            # Base queryset for all notifications
            queryset = Notification.objects.filter(
                recipient=self.request.user
            ).select_related(
                'content_type'
            )

            # Filter trade notifications based on subscription level
            if subscription.plan.name in ['BASIC', 'PREMIUM']:
                # Get accessible trades based on subscription
                accessible_trades = Trade.get_trades_for_subscription(self.request.user, subscription)
                
                # Filter notifications to only include accessible trades
                queryset = queryset.filter(
                    Q(content_type__model='tradenotification') & 
                    Q(object_id__in=accessible_trades.values_list('id', flat=True))
                )
            # SUPER_PREMIUM users get all notifications without filtering

            return queryset.order_by('-created_at')

        except Exception as e:
            logger.error(f"Error getting notifications for user {self.request.user.id}: {str(e)}")
            return Notification.objects.none()
    
    def list(self, request, *args, **kwargs):
        """
        List notifications with additional filtering options.
        
        Query Parameters:
            - is_read: Filter by read status (true/false)
            - notification_type: Filter by notification type
            - start_date: Filter by start date
            - end_date: Filter by end date
            
        Returns:
            Response: Paginated list of notifications with unread count
        """
        try:
            queryset = self.get_queryset()
            
            # Apply read status filter
            is_read = request.query_params.get('is_read')
            if is_read is not None:
                is_read = is_read.lower() == 'true'
                queryset = queryset.filter(is_read=is_read)
            
            # Apply notification type filter
            notification_type = request.query_params.get('notification_type')
            if notification_type:
                queryset = queryset.filter(notification_type=notification_type)
            
            # Apply date range filters
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            if start_date:
                queryset = queryset.filter(created_at__gte=start_date)
            if end_date:
                queryset = queryset.filter(created_at__lte=end_date)
            
            # Get unread count for all notifications
            unread_count = self.get_queryset().filter(is_read=False).count()
            
            # Paginate and return results
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                response = self.get_paginated_response(serializer.data)
                response.data['unread_count'] = unread_count
                return response
            
            serializer = self.get_serializer(queryset, many=True)
            return Response({
                'results': serializer.data,
                'unread_count': unread_count
            })

        except Exception as e:
            logger.error(f"Error listing notifications: {str(e)}")
            return Response({
                'error': 'Error retrieving notifications'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """
        Mark a single notification as read.
        
        Args:
            pk: Notification ID
            
        Returns:
            Response: Updated notification data
        """
        try:
            notification = self.get_object()
            notification.is_read = True
            notification.save()
            return Response(self.get_serializer(notification).data)
        except Exception as e:
            logger.error(f"Error marking notification as read: {str(e)}")
            return Response({
                'error': 'Error marking notification as read'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def mark_unread(self, request, pk=None):
        """
        Mark a single notification as unread.
        
        Args:
            pk: Notification ID
            
        Returns:
            Response: Updated notification data
        """
        try:
            notification = self.get_object()
            notification.is_read = False
            notification.save()
            return Response(self.get_serializer(notification).data)
        except Exception as e:
            logger.error(f"Error marking notification as unread: {str(e)}")
            return Response({
                'error': 'Error marking notification as unread'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """
        Mark all notifications as read with optional filters.
        
        Request Body:
            - notification_type: Filter by notification type
            - before_date: Filter by date
            
        Returns:
            Response: Count of marked notifications
        """
        try:
            # Get base queryset of unread notifications
            queryset = self.get_queryset().filter(is_read=False)
            
            # Apply notification type filter
            notification_type = request.data.get('notification_type')
            if notification_type:
                queryset = queryset.filter(notification_type=notification_type)
            
            # Apply date filter
            before_date = request.data.get('before_date')
            if before_date:
                queryset = queryset.filter(created_at__lte=before_date)
            
            # Update notifications
            updated_count = queryset.update(
                is_read=True,
                updated_at=timezone.now()
            )
            
            return Response({
                'status': 'success',
                'marked_read': updated_count
            })

        except Exception as e:
            logger.error(f"Error marking all notifications as read: {str(e)}")
            return Response({
                'error': 'Error marking notifications as read'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def trade_notifications(self, request):
        """
        Get trade-specific notifications based on subscription level.
        
        Query Parameters:
            - is_read: Filter by read status (true/false)
            
        Returns:
            Response: Paginated list of trade notifications
        """
        try:
            # Get user's active subscription
            subscription = Subscription.objects.select_related('plan').filter(
                user=request.user,
                is_active=True,
                start_date__lte=timezone.now(),
                end_date__gte=timezone.now()
            ).first()

            if not subscription:
                return Response({
                    'error': 'No active subscription found'
                }, status=status.HTTP_403_FORBIDDEN)

            # Get accessible trades based on subscription
            accessible_trades = Trade.get_trades_for_subscription(request.user, subscription)
            
            # Get notifications for accessible trades with related data
            queryset = TradeNotification.objects.filter(
                trade__in=accessible_trades,
                user=request.user
            ).select_related(
                'trade',
                'trade__company'
            ).order_by('-created_at')

            # Apply read status filter
            is_read = request.query_params.get('is_read')
            if is_read is not None:
                is_read = is_read.lower() == 'true'
                queryset = queryset.filter(is_read=is_read)

            # Paginate and return results
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting trade notifications: {str(e)}")
            return Response({
                'error': 'Error retrieving trade notifications'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def subscription_notifications(self, request):
        """
        Get subscription-specific notifications.
        
        Query Parameters:
            - is_read: Filter by read status (true/false)
            - subscription_type: Filter by subscription type (BASIC, PREMIUM, SUPER_PREMIUM)
            
        Returns:
            Response: Paginated list of subscription notifications
        """
        try:
            # Get user's active subscription
            subscription = Subscription.objects.select_related('plan').filter(
                user=request.user,
                is_active=True,
                start_date__lte=timezone.now(),
                end_date__gte=timezone.now()
            ).first()

            if not subscription:
                return Response({
                    'error': 'No active subscription found'
                }, status=status.HTTP_403_FORBIDDEN)

            # Get subscription-specific notifications
            queryset = Notification.objects.filter(
                recipient=request.user,
                notification_type__in=[
                    'SUBSCRIPTION_STARTED',
                    'SUBSCRIPTION_RENEWED',
                    'SUBSCRIPTION_EXPIRED',
                    'SUBSCRIPTION_UPGRADED',
                    'SUBSCRIPTION_DOWNGRADED'
                ]
            ).select_related(
                'content_type'
            ).order_by('-created_at')

            # Apply subscription type filter
            subscription_type = request.query_params.get('subscription_type')
            if subscription_type:
                queryset = queryset.filter(
                    data__contains={'subscription_type': subscription_type}
                )

            # Apply read status filter
            is_read = request.query_params.get('is_read')
            if is_read is not None:
                is_read = is_read.lower() == 'true'
                queryset = queryset.filter(is_read=is_read)

            # Add subscription info to response
            subscription_info = {
                'plan': subscription.plan.name,
                'start_date': subscription.start_date.isoformat(),
                'end_date': subscription.end_date.isoformat(),
                'is_active': subscription.is_active
            }

            # Paginate and return results
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                response = self.get_paginated_response(serializer.data)
                response.data['subscription'] = subscription_info
                return response

            serializer = self.get_serializer(queryset, many=True)
            return Response({
                'results': serializer.data,
                'subscription': subscription_info
            })

        except Exception as e:
            logger.error(f"Error getting subscription notifications: {str(e)}")
            return Response({
                'error': 'Error retrieving subscription notifications'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)