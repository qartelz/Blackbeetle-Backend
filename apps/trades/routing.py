from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Handle token in URL path
    re_path(r'ws/trade-updates/(?P<token>[^/]+)/$', consumers.TradeUpdatesConsumer.as_asgi()),
    # Handle token in query parameters
    re_path(r'ws/trade-updates/$', consumers.TradeUpdatesConsumer.as_asgi()),
]

