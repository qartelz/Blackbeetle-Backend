from django.urls import path
from .views import (
    InstitutionListView,
    InstitutionDetailView,
    InstitutionUsersView,
    InstitutionStatsView,

    # B2BAdminUserListView,
    # B2BAdminUserActionView,
    # B2BAdminUserStatsView

    B2BUserListCreateView,
    B2BUserDetailView,
    B2BUserBulkActionView,
    B2BAdminStatsView,
    B2BAdminDetailedUserStatsView
)

urlpatterns = [
    path('institutions/', InstitutionListView.as_view(), name='institution-list'),
    path('institutions/<int:id>/', InstitutionDetailView.as_view(), name='institution-detail'),
    path('institutions/<int:institution_id>/users/', InstitutionUsersView.as_view(), name='institution-users'),
    path('institutions/stats/', InstitutionStatsView.as_view(), name='institution-stats'),


     # B2B Admin User Management URLs
    # path('b2b-admin/users/', B2BAdminUserListView.as_view(), name='b2b-admin-user-list'),
    # path('b2b-admin/users/<int:user_id>/action/', B2BAdminUserActionView.as_view(), name='b2b-admin-user-action'),
    # path('b2b-admin/users/stats/', B2BAdminUserStatsView.as_view(), name='b2b-admin-user-stats'),

    path('b2b-admin/users/', B2BUserListCreateView.as_view(), name='b2b-admin-user-list-create'),
    path('b2b-admin/users/<int:user_id>/', B2BUserDetailView.as_view(), name='b2b-admin-user-detail'),
    path('b2b-admin/users/bulk-action/', B2BUserBulkActionView.as_view(), name='b2b-admin-user-bulk-action'),
    path('b2b-admin/stats/', B2BAdminStatsView.as_view(), name='b2b-admin-stats'),
    path('b2b-admin/stats/users/<int:user_id>/', B2BAdminDetailedUserStatsView.as_view(), name='b2b-admin-user-stats'),

]


# from django.urls import path
# from .views import (
#     InstitutionListView,
#     InstitutionDetailView,
#     InstitutionUsersView,
# )

# urlpatterns = [
#     path('institutions/', InstitutionListView.as_view(), name='institution-list'),
#     path('institutions/<int:id>/', InstitutionDetailView.as_view(), name='institution-detail'),
#     path('institutions/<int:institution_id>/users/', InstitutionUsersView.as_view(), name='institution-users'),
# ]