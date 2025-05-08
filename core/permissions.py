
from rest_framework import generics, permissions
from apps.subscriptions.models import Subscription
from django.utils import timezone
class IsAdminOrSubscribedUser(permissions.BasePermission):
    def has_permission(self, request, view):
        
        if request.user.is_staff:
            return True
        if request.user.is_authenticated:
            subscription = Subscription.objects.filter(
                user=request.user,
                is_active=True,
                end_date__gte=timezone.now().date()
            ).first()
            return subscription is not None
        return False
    
class IsB2BAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_b2b_admin

class IsB2BUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_b2b_user

class IsB2CUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_b2c_user

