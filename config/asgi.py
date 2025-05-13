import os
import django

# Set up Django first, before any other imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

# Now import Django-related modules after setup
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from apps.trades.routing import websocket_urlpatterns as trade_websocket_urlpatterns
from apps.notifications.routing import websocket_urlpatterns as notification_websocket_urlpatterns
from core.middleware import JWTAuthMiddleware

combined_websocket_patterns = trade_websocket_urlpatterns + notification_websocket_urlpatterns

# Define the application
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(
        URLRouter(
            combined_websocket_patterns
        )
    ),
})