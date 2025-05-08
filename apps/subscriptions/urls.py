from django.urls import path
from .views import (
    PlanListCreateView,
    PlanDetailView,
    OrderListCreateView,
    OrderDetailView,
    CompleteRazorpayPaymentView,
    CompleteOfflinePaymentView,
    SubscriptionListView,
    SubscriptionDetailView,
    CancelSubscriptionView,
    # AdminOrderCreateView,
    # AdminCompleteOfflinePaymentView,
    InstitutionListView,
    InstitutionUsersView,
    AvailableB2BPlansView,
    AdminOrderListCreateView,
    AdminOrderDetailView,
    AdminOrderOfflinePaymentView
)



urlpatterns = [
    # Plan URLs
    path('plans/', PlanListCreateView.as_view(), name='plan-list-create'),
    path('plans/<int:pk>/', PlanDetailView.as_view(), name='plan-detail'),

    # Order URLs
    path('orders/',OrderListCreateView.as_view(), name='order-list-create'),
    path('orders/<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
    path('orders/<int:pk>/complete-razorpay/', CompleteRazorpayPaymentView.as_view(), name='complete-razorpay-payment'),
    path('orders/<int:pk>/complete-offline/', CompleteOfflinePaymentView.as_view(), name='complete-offline-payment'),

    # Subscription URLs
    path('subscriptions/', SubscriptionListView.as_view(), name='subscription-list'),
    path('subscriptions/<int:pk>/', SubscriptionDetailView.as_view(), name='subscription-detail'),
    path('subscriptions/<int:pk>/cancel/', CancelSubscriptionView.as_view(), name='cancel-subscription'),

    # New admin-only URL patterns
    # path('admin/orders/create/', AdminOrderCreateView.as_view(), name='admin-order-create'),
    # path('admin/orders/<int:pk>/complete-offline/', AdminCompleteOfflinePaymentView.as_view(), name='admin-complete-offline-payment'),



    # Admin-only URL patterns
    # path('admin/orders/', AdminOrderCreateView.as_view(), name='admin-order-list-create'),
    # path('admin/orders/<int:pk>/complete-offline/', AdminCompleteOfflinePaymentView.as_view(), name='admin-complete-offline-payment'),
    path('admin/institutions/', InstitutionListView.as_view(), name='admin-institution-list'),
    path('admin/institutions/<int:institution_id>/users/', InstitutionUsersView.as_view(), name='admin-institution-users'),
    path('admin/plans/b2b/', AvailableB2BPlansView.as_view(), name='admin-available-b2b-plans'),
    # path('admin/orders/create/', AdminOrderCreateView.as_view(), name='admin-order-create'),
    path('admin/orders/', AdminOrderListCreateView.as_view(), name='admin-order-list'),
    path('admin/orders/<uuid:id>/', AdminOrderDetailView.as_view(), name='admin-order-detail'),
    path('admin/orders/<int:order_id>/offline-payment/', AdminOrderOfflinePaymentView.as_view(), name='admin-order-offline-payment'),
]