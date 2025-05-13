from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API v1 endpoints
    path('api/v1/', include([
        # User management
        path('users/', include('apps.users.urls')),
        
        # Notifications
        path('notifications/', include('apps.notifications.urls')),
        
        # Trades
        path('trades/', include('apps.trades.urls')),
        
        # Subscriptions
        path('subscriptions/', include('apps.subscriptions.urls')),
        
        # Other apps...
    ])),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 