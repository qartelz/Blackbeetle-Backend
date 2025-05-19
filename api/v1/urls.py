from django.urls import path, include

urlpatterns = [
    path('institutions/', include('apps.institutions.urls')),
    path('users/', include('apps.users.urls')),
    path('trades/', include('apps.trades.urls')),
    path('subscriptions/', include('apps.subscriptions.urls')),
    path('analytics/', include('apps.analytics.urls')),
    path('index-and-commodity/', include('apps.indexAndCommodity.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('events/', include('apps.events.urls')),
    path('accuracy/', include('apps.accuracy.urls')),
    path('stockreports/', include('apps.stockreports.urls')),
]

