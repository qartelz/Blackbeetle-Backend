from django.urls import path
from .views import (
    LoginView, B2CRegistrationView, B2BUserRegistrationView, B2BAdminRegistrationView,
    UserProfileView, LogoutView, B2BAdminDashboardView, B2BUserDashboardView,
    B2CDashboardView, AdminDashboardView, SubscriptionView, CustomTokenRefreshView, 
    UserListView, UserActionView, UserStatsView, LoginAttemptView,InstitutionUserManagementView,
    RequestPasswordResetView,VerifyOTPView,ResetPasswordView, UserProfileEditView,VerifyNewDeviceOTPView
)

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('register/b2c/', B2CRegistrationView.as_view(), name='register-b2c'),
    path('register/b2b-user/', B2BUserRegistrationView.as_view(), name='register-b2b-user'),
    path('register/b2b-admin/', B2BAdminRegistrationView.as_view(), name='register-b2b-admin'),
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('logout/', LogoutView.as_view(), name='logout'),

    path('verify-new-device-otp/', VerifyNewDeviceOTPView.as_view(), name='verify-new-device-otp'),
    path('dashboard/b2b-admin/', B2BAdminDashboardView.as_view(), name='b2b-admin-dashboard'),
    path('dashboard/b2b-user/', B2BUserDashboardView.as_view(), name='b2b-user-dashboard'),
    path('dashboard/b2c/', B2CDashboardView.as_view(), name='b2c-dashboard'),
    path('dashboard/admin/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('subscription/', SubscriptionView.as_view(), name='user-subscription'),
    path('users/', UserListView.as_view(), name='user-list'),
    path('users/<uuid:user_id>/action/', UserActionView.as_view(), name='user-action'),
    path('users/stats/', UserStatsView.as_view(), name='user-stats'),
    path('users/<uuid:user_id>/login-attempts/', LoginAttemptView.as_view(), name='login-attempts'),

    path('b2b-users/',InstitutionUserManagementView.as_view(),name='institution-users-list'),
    path('b2b-users/<uuid:user_id>/',InstitutionUserManagementView.as_view(),name='institution-user-detail'),


    path('profiles/', UserProfileView.as_view(), name='user-profile'),
    path('profile/edit/', UserProfileEditView.as_view(), name='profile-edit'),



    path('request-password-reset/', RequestPasswordResetView.as_view(), name='request-password-reset'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset-password'),
]

