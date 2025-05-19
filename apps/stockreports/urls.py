from django.urls import path
from . import views

app_name = "stockreports"

urlpatterns = [
    path('', views.StockReportListView.as_view(), name='list'),
    path('create/', views.StockReportCreateView.as_view(), name='create'),
    path('<int:pk>/', views.StockReportDetailView.as_view(), name='detail'),
    path('<int:pk>/update/', views.StockReportUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.StockReportDeleteView.as_view(), name='delete'),
]