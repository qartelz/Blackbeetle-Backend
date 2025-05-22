from django.urls import path
from .views import (
<<<<<<< Updated upstream
    CreateStockReportView,
    ListStockReportsView,
    StockReportDetailView,
    UpdateStockReportView,
    DeleteStockReportView,
    DownloadPDFView
=======
    StockReportListView,
    StockReportDetailView,
    StockReportCreateView,
    StockReportUpdateView,
    StockReportDeleteView
>>>>>>> Stashed changes
)

app_name = 'stockreports'

urlpatterns = [
<<<<<<< Updated upstream
    # Basic CRUD operations
    path('create/', CreateStockReportView.as_view(), name='create-report'),
    path('list/', ListStockReportsView.as_view(), name='list-reports'),
    path('detail/<int:pk>/', StockReportDetailView.as_view(), name='report-detail'),
    path('update/<int:pk>/', UpdateStockReportView.as_view(), name='update-report'),
    path('delete/<int:pk>/', DeleteStockReportView.as_view(), name='delete-report'),
    
    # PDF download
    path('download/<int:pk>/', DownloadPDFView.as_view(), name='download-pdf'),
=======
    # List all stock reports with filtering
    path('list/', StockReportListView.as_view(), name='list'),
    
    # Create new stock report
    path('create/', StockReportCreateView.as_view(), name='create'),
    
    # Get specific stock report details
    path('<int:pk>/detail/', StockReportDetailView.as_view(), name='detail'),
    
    # Update stock report
    path('<int:pk>/update/', StockReportUpdateView.as_view(), name='update'),
    
    # Delete stock report
    path('<int:pk>/delete/', StockReportDeleteView.as_view(), name='delete'),
>>>>>>> Stashed changes
]