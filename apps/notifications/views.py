from .serializers import NotificationSerializer
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Notification

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user
        ).select_related(
            'content_type'
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
        
        # Paginate results
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
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a single notification as read"""
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response(self.get_serializer(notification).data)
    
    @action(detail=True, methods=['post'])
    def mark_unread(self, request, pk=None):
        """Mark a single notification as unread"""
        notification = self.get_object()
        notification.is_read = False
        notification.save()
        return Response(self.get_serializer(notification).data)
    
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