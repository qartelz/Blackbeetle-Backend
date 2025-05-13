from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet

router = DefaultRouter()
router.register(r'', NotificationViewSet, basename='notifications')

urlpatterns = [
    # Include the router URLs
    path('', include(router.urls)),
    
    # Additional notification endpoints
    path('trade-updates/', NotificationViewSet.as_view({'get': 'trade_notifications'}), name='trade-notifications'),
    path('subscription/', NotificationViewSet.as_view({'get': 'subscription_notifications'}), name='subscription-notifications'),
    path('mark-all-read/', NotificationViewSet.as_view({'post': 'mark_all_read'}), name='mark-all-read'),
]