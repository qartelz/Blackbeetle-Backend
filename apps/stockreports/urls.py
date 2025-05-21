from django.urls import path
from .views import (
    CreateStockReportView,
    ListStockReportsView,
    StockReportDetailView,
    UpdateStockReportView,
    DeleteStockReportView,
    DownloadPDFView
)

app_name = 'stockreports'

urlpatterns = [
    # Basic CRUD operations
    path('create/', CreateStockReportView.as_view(), name='create-report'),
    path('list/', ListStockReportsView.as_view(), name='list-reports'),
    path('detail/<int:pk>/', StockReportDetailView.as_view(), name='report-detail'),
    path('update/<int:pk>/', UpdateStockReportView.as_view(), name='update-report'),
    path('delete/<int:pk>/', DeleteStockReportView.as_view(), name='delete-report'),
    
    # PDF download
    path('download/<int:pk>/', DownloadPDFView.as_view(), name='download-pdf'),
]