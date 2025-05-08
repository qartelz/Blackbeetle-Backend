from rest_framework import generics, filters, status
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django_filters import rest_framework as django_filters
from rest_framework.pagination import PageNumberPagination
from .models import Institution, InstitutionUser
from .serializers import (
    InstitutionListSerializer,
    InstitutionDetailSerializer,
    InstitutionUserListSerializer,

    B2BUserCreateSerializer,
    B2BUserDetailSerializer,
    B2BUserUpdateSerializer,

)
from ..users.models import User

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters import rest_framework as filterss
from django.db.models import Q

from core.permissions import IsB2BAdmin
from .models import InstitutionUser, Institution
from django.db.models import Count

from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models.functions import TruncMonth, TruncYear
class CustomPagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = 'page_size'
    max_page_size = 100

class InstitutionFilter(django_filters.FilterSet):
    class Meta:
        model = Institution
        fields = {
            'name': ['icontains'],
            'code': ['exact', 'icontains'],
            'is_active': ['exact'],
            'created_at': ['gte', 'lte'],
        }

class InstitutionListView(generics.ListAPIView):
    queryset = Institution.objects.all()
    serializer_class = InstitutionListSerializer
    permission_classes = [IsAdminUser]
    pagination_class = CustomPagination
    filter_backends = [django_filters.DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = InstitutionFilter
    search_fields = ['name', 'code', 'contact_email']
    ordering_fields = ['name', 'created_at', 'is_active']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = Institution.objects.all()
        is_active = self.request.query_params.get('is_active', None)
        
        if is_active is not None:
            is_active = is_active.lower() == 'true'
            queryset = queryset.filter(is_active=is_active)
            
        return queryset

class InstitutionDetailView(generics.RetrieveUpdateAPIView):
    queryset = Institution.objects.all()
    serializer_class = InstitutionDetailSerializer
    permission_classes = [IsAdminUser]
    lookup_field = 'id'

class InstitutionUsersView(generics.ListAPIView):
    serializer_class = InstitutionUserListSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [django_filters.DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'user__first_name', 'user__last_name', 
        'user__email', 'user__phone_number',
        'code'
    ]
    ordering_fields = ['join_date', 'is_active', 'role']
    ordering = ['-join_date']

    def get_queryset(self):
        institution_id = self.kwargs.get('institution_id')
        return InstitutionUser.objects.filter(
            institution_id=institution_id
        ).select_related('user', 'institution')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class InstitutionStatsView(generics.RetrieveAPIView):
    permission_classes = [IsAdminUser]
    
    def retrieve(self, request, *args, **kwargs):
        total_institutions = Institution.objects.count()
        total_users = User.objects.filter(user_type=User.UserType.B2B_USER).count()
        active_admins = User.objects.filter(user_type=User.UserType.B2B_ADMIN, is_active=True).count()

        return Response({
            "total_institutions": total_institutions,
            "total_users": total_users,
            "active_admins": active_admins
        })


class B2BUserListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsB2BAdmin]

    def get(self, request):
        """List all users in the admin's institution"""
        institution = request.user.administered_institution
        if not institution:
            return Response(
                {"error": "No institution found for this admin"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Get query parameters
        search = request.GET.get('search', '')
        is_active = request.GET.get('is_active')
        role = request.GET.get('role')
        
        # Base queryset
        users = User.objects.filter(
            institution_memberships__institution=institution,
            user_type=User.UserType.B2B_USER
        )

        # Apply filters
        if search:
            users = users.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone_number__icontains=search)
            )

        if is_active is not None:
            is_active = is_active.lower() == 'true'
            users = users.filter(is_active=is_active)

        if role:
            users = users.filter(institution_memberships__role=role)

        # Serialize and return
        serializer = B2BUserDetailSerializer(users, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Create a new B2B user"""
        institution = request.user.administered_institution
        if not institution:
            return Response(
                {"error": "No institution found for this admin"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = B2BUserCreateSerializer(data=request.data)
        if serializer.is_valid():
            # Check if institution has reached max users
            if not institution.can_add_user():
                return Response(
                    {"error": "Maximum number of users reached for this institution"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create user
            user_data = serializer.validated_data
            role = user_data.pop('role', 'MEMBER')
            password = user_data.pop('password')
            
            user = User.objects.create_user(
                **user_data,
                user_type=User.UserType.B2B_USER
            )
            user.set_password(password)
            user.save()

            # Create institution user
            InstitutionUser.objects.create(
                user=user,
                institution=institution,
                role=role
            )

            return Response(
                B2BUserDetailSerializer(user).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class B2BUserDetailView(APIView):
    permission_classes = [IsAuthenticated, IsB2BAdmin]

    def get_user(self, user_id, institution):
        try:
            return User.objects.get(
                id=user_id,
                institution_memberships__institution=institution,
                user_type=User.UserType.B2B_USER
            )
        except User.DoesNotExist:
            return None

    def get(self, request, user_id):
        """Get details of a specific user"""
        institution = request.user.administered_institution
        if not institution:
            return Response(
                {"error": "No institution found for this admin"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        user = self.get_user(user_id, institution)
        if not user:
            return Response(
                {"error": "User not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = B2BUserDetailSerializer(user)
        return Response(serializer.data)

    def put(self, request, user_id):
        """Update a specific user"""
        institution = request.user.administered_institution
        if not institution:
            return Response(
                {"error": "No institution found for this admin"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        user = self.get_user(user_id, institution)
        if not user:
            return Response(
                {"error": "User not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = B2BUserUpdateSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            # Update user
            user_data = serializer.validated_data
            role = user_data.pop('role', None)
            
            for attr, value in user_data.items():
                setattr(user, attr, value)
            user.save()

            # Update role if provided
            if role:
                institution_user = user.institution_memberships.filter(
                    institution=institution
                ).first()
                if institution_user:
                    institution_user.role = role
                    institution_user.save()

            return Response(B2BUserDetailSerializer(user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, user_id):
        """Delete a specific user"""
        institution = request.user.administered_institution
        if not institution:
            return Response(
                {"error": "No institution found for this admin"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        user = self.get_user(user_id, institution)
        if not user:
            return Response(
                {"error": "User not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Delete institution user relationship
        InstitutionUser.objects.filter(
            user=user,
            institution=institution
        ).delete()

        # Optional: Delete the user completely if they don't belong to any other institution
        if not user.institution_memberships.exists():
            user.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

class B2BUserBulkActionView(APIView):
    permission_classes = [IsAuthenticated, IsB2BAdmin]

    def post(self, request):
        """Perform bulk actions on users"""
        institution = request.user.administered_institution
        if not institution:
            return Response(
                {"error": "No institution found for this admin"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        action = request.data.get('action')
        user_ids = request.data.get('user_ids', [])

        if not user_ids:
            return Response(
                {"error": "No users specified"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        users = User.objects.filter(
            id__in=user_ids,
            institution_memberships__institution=institution,
            user_type=User.UserType.B2B_USER
        )

        if action == 'activate':
            users.update(is_active=True)
        elif action == 'deactivate':
            users.update(is_active=False)
        elif action == 'delete':
            InstitutionUser.objects.filter(
                user__in=users,
                institution=institution
            ).delete()
            # Delete users that don't belong to any other institution
            for user in users:
                if not user.institution_memberships.exists():
                    user.delete()
        else:
            return Response(
                {"error": "Invalid action"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"message": f"Bulk {action} completed successfully"})



class B2BAdminStatsView(APIView):
    permission_classes = [IsAuthenticated, IsB2BAdmin]

    def get(self, request):
        """Get comprehensive statistics for B2B admin's institution"""
        institution = request.user.administered_institution
        if not institution:
            return Response(
                {"error": "No institution found for this admin"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Time periods for filtering
        now = timezone.now()
        today = now.date()
        thirty_days_ago = today - timedelta(days=30)
        this_year = now.year

        # Get all users from the institution
        institution_users = InstitutionUser.objects.filter(
            institution=institution
        )

        # Base user queryset
        users = User.objects.filter(
            institution_memberships__institution=institution,
            user_type=User.UserType.B2B_USER
        )

        # Overall Stats
        overall_stats = {
            'total_users': users.count(),
            'active_users': users.filter(is_active=True).count(),
            'inactive_users': users.filter(is_active=False).count(),
            'verified_users': users.filter(is_verified=True).count(),
            'capacity': {
                'total': institution.max_users,
                'used': users.count(),
                'available': institution.max_users - users.count(),
                'utilization_percentage': (users.count() / institution.max_users * 100) if institution.max_users > 0 else 0
            }
        }

        # Role Distribution
        role_stats = institution_users.values('role').annotate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True))
        ).order_by('role')

        # Growth Stats
        monthly_growth = institution_users.annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            new_users=Count('id')
        ).order_by('-month')[:12]

        yearly_growth = institution_users.annotate(
            year=TruncYear('created_at')
        ).values('year').annotate(
            new_users=Count('id')
        ).order_by('-year')

        # Recent Activity
        recent_stats = {
            'new_users_today': institution_users.filter(
                created_at__date=today
            ).count(),
            'new_users_this_month': institution_users.filter(
                created_at__month=now.month,
                created_at__year=now.year
            ).count(),
            'new_users_this_year': institution_users.filter(
                created_at__year=this_year
            ).count(),
            'recent_registrations': list(users.filter(
                date_joined__gte=thirty_days_ago
            ).values('id', 'first_name', 'last_name', 'email', 'date_joined')
            .order_by('-date_joined')[:5])
        }

        # User Status Changes
        status_changes = {
            'recent_deactivations': list(users.filter(
                is_active=False,
                institution_memberships__updated_at__gte=thirty_days_ago
            ).values('id', 'first_name', 'last_name', 'email')[:5]),
            'recent_activations': list(users.filter(
                is_active=True,
                institution_memberships__updated_at__gte=thirty_days_ago
            ).values('id', 'first_name', 'last_name', 'email')[:5])
        }

        # Engagement Metrics (if applicable to your system)
        engagement_stats = {
            'login_frequency': {
                'daily_active': users.filter(
                    last_login__date=today
                ).count(),
                'weekly_active': users.filter(
                    last_login__gte=today - timedelta(days=7)
                ).count(),
                'monthly_active': users.filter(
                    last_login__gte=thirty_days_ago
                ).count()
            }
        }

        return Response({
            'timestamp': now,
            'overall_stats': overall_stats,
            'role_distribution': list(role_stats),
            'growth': {
                'monthly': list(monthly_growth),
                'yearly': list(yearly_growth)
            },
            'recent_activity': recent_stats,
            'status_changes': status_changes,
            'engagement': engagement_stats
        })

class B2BAdminDetailedUserStatsView(APIView):
    permission_classes = [IsAuthenticated, IsB2BAdmin]

    def get(self, request, user_id):
        """Get detailed statistics for a specific user"""
        institution = request.user.administered_institution
        if not institution:
            return Response(
                {"error": "No institution found for this admin"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            user = User.objects.get(
                id=user_id,
                institution_memberships__institution=institution,
                user_type=User.UserType.B2B_USER
            )
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        institution_user = user.institution_memberships.get(institution=institution)

        user_stats = {
            'user_info': {
                'id': user.id,
                'name': f"{user.first_name} {user.last_name}",
                'email': user.email,
                'phone_number': str(user.phone_number),
                'is_active': user.is_active,
                'is_verified': user.is_verified
            },
            'institution_info': {
                'role': institution_user.role,
                'join_date': institution_user.join_date,
                'institution_code': institution_user.code,
                'days_in_institution': (timezone.now().date() - institution_user.join_date).days
            },
            'activity': {
                'last_login': user.last_login,
                'date_joined': user.date_joined,
                'profile_completion': self.calculate_profile_completion(user)
            }
        }

        return Response(user_stats)

    def calculate_profile_completion(self, user):
        """Calculate the profile completion percentage"""
        fields = ['first_name', 'last_name', 'email', 'phone_number', 
                 'date_of_birth', 'bio']
        filled_fields = sum(1 for field in fields if getattr(user, field))
        return (filled_fields / len(fields)) * 100

# class B2BUserFilter(filterss.FilterSet):
#     status = filterss.BooleanFilter(field_name='is_active')
#     search = filterss.CharFilter(method='filter_search')
    
#     class Meta:
#         model = User
#         fields = ['status']
    
#     def filter_search(self, queryset, name, value):
#         return queryset.filter(
#             Q(first_name__icontains=value) |
#             Q(last_name__icontains=value) |
#             Q(email__icontains=value) |
#             Q(phone_number__icontains=value)
#         )

# class StandardResultsSetPagination(PageNumberPagination):
#     page_size = 10
#     page_size_query_param = 'page_size'
#     max_page_size = 100

# class B2BAdminUserListView(APIView):
#     permission_classes = [IsB2BAdmin]
#     pagination_class = StandardResultsSetPagination

#     def get(self, request):
#         institution = request.user.administered_institution
#         if not institution:
#             return Response(
#                 {"error": "No institution found for this admin"}, 
#                 status=status.HTTP_404_NOT_FOUND
#             )

#         # Get all users from admin's institution
#         users = User.objects.filter(
#             institution_memberships__institution=institution,
#             user_type=User.UserType.B2B_USER
#         )

#         # Apply filters
#         filter_backend = B2BUserFilter(
#             request.GET, 
#             queryset=users
#         )
#         filtered_users = filter_backend.qs

#         # Apply pagination
#         paginator = self.pagination_class()
#         paginated_users = paginator.paginate_queryset(filtered_users, request)

#         # Serialize the data
#         user_data = [{
#             'id': user.id,
#             'first_name': user.first_name,
#             'last_name': user.last_name,
#             'email': user.email,
#             'phone_number': str(user.phone_number),
#             'is_active': user.is_active,
#             'is_verified': user.is_verified,
#             'date_joined': user.date_joined,
#             'institution_user': {
#                 'code': user.institution_memberships.get(institution=institution).code,
#                 'role': user.institution_memberships.get(institution=institution).role,
#                 'join_date': user.institution_memberships.get(institution=institution).join_date
#             }
#         } for user in paginated_users]

#         return Response({
#             'count': filtered_users.count(),
#             'results': user_data,
#             'next': paginator.get_next_link(),
#             'previous': paginator.get_previous_link()
#         })

# class B2BAdminUserActionView(APIView):
#     permission_classes = [IsB2BAdmin]

#     def put(self, request, user_id):
#         institution = request.user.administered_institution
#         if not institution:
#             return Response(
#                 {"error": "No institution found for this admin"}, 
#                 status=status.HTTP_404_NOT_FOUND
#             )

#         try:
#             institution_user = InstitutionUser.objects.get(
#                 user_id=user_id,
#                 institution=institution
#             )
#         except InstitutionUser.DoesNotExist:
#             return Response(
#                 {"error": "User not found in your institution"}, 
#                 status=status.HTTP_404_NOT_FOUND
#             )

#         action = request.data.get('action')
#         if action == 'update':
#             # Update user details
#             user_data = request.data.get('user_data', {})
#             user = institution_user.user
            
#             allowed_fields = ['first_name', 'last_name', 'email']
#             for field in allowed_fields:
#                 if field in user_data:
#                     setattr(user, field, user_data[field])
            
#             # Update institution user details
#             if 'role' in user_data:
#                 institution_user.role = user_data['role']
            
#             user.save()
#             institution_user.save()
            
#         elif action == 'deactivate':
#             institution_user.is_active = False
#             institution_user.save()
            
#         elif action == 'activate':
#             institution_user.is_active = True
#             institution_user.save()
            
#         elif action == 'delete':
#             institution_user.delete()
#             return Response(status=status.HTTP_204_NO_CONTENT)
            
#         else:
#             return Response(
#                 {"error": "Invalid action"}, 
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         return Response({
#             "message": f"User {action}d successfully",
#             "user_id": user_id
#         })

# class B2BAdminUserStatsView(APIView):
#     permission_classes = [IsB2BAdmin]

#     def get(self, request):
#         institution = request.user.administered_institution
#         if not institution:
#             return Response(
#                 {"error": "No institution found for this admin"}, 
#                 status=status.HTTP_404_NOT_FOUND
#             )

#         # Get all users from the institution
#         institution_users = InstitutionUser.objects.filter(institution=institution)

#         # Calculate various stats
#         stats = {
#             'total_users': institution_users.count(),
#             'active_users': institution_users.filter(is_active=True).count(),
#             'inactive_users': institution_users.filter(is_active=False).count(),
#             'users_by_role': institution_users.values('role').annotate(
#                 count=Count('id')
#             ),
#             'recent_joins': institution_users.order_by('-join_date')[:5].values(
#                 'user__first_name', 
#                 'user__last_name', 
#                 'join_date'
#             ),
#             'capacity_used': (institution_users.count() / institution.max_users) * 100
#         }

#         return Response(stats)
# # from rest_framework import generics, filters, status
# # from rest_framework.response import Response
# # from rest_framework.permissions import IsAdminUser
# # from rest_framework.views import APIView
# # from django_filters import rest_framework as django_filters
# # from .models import Institution, InstitutionUser
# # from ..users.models import User
# # from .serializers import (
# #     InstitutionListSerializer,
# #     InstitutionDetailSerializer,
# #     InstitutionUserListSerializer
# # )

# # class InstitutionFilter(django_filters.FilterSet):
# #     class Meta:
# #         model = Institution
# #         fields = {
# #             'name': ['icontains'],
# #             'code': ['exact', 'icontains'],
# #             'is_active': ['exact'],
# #             'created_at': ['gte', 'lte'],
# #         }

# # class InstitutionListView(generics.ListAPIView):
# #     queryset = Institution.objects.all()
# #     serializer_class = InstitutionListSerializer
# #     # permission_classes = [IsAdminUser]
# #     filter_backends = [django_filters.DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
# #     filterset_class = InstitutionFilter
# #     search_fields = ['name', 'code', 'contact_email']
# #     ordering_fields = ['name', 'created_at', 'is_active']
# #     ordering = ['-created_at']

# # class InstitutionDetailView(generics.RetrieveUpdateAPIView):
# #     queryset = Institution.objects.all()
# #     serializer_class = InstitutionDetailSerializer
# #     # permission_classes = [IsAdminUser]
# #     lookup_field = 'id'

# # class InstitutionUsersView(generics.ListAPIView):
# #     serializer_class = InstitutionUserListSerializer
# #     # permission_classes = [IsAdminUser]
# #     filter_backends = [django_filters.DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
# #     search_fields = [
# #         'user__first_name', 'user__last_name', 
# #         'user__email', 'user__phone_number',
# #         'code'
# #     ]
# #     ordering_fields = ['join_date', 'is_active', 'role']
# #     ordering = ['-join_date']

# #     def get_queryset(self):
# #         institution_id = self.kwargs.get('institution_id')
# #         return InstitutionUser.objects.filter(
# #             institution_id=institution_id
# #         ).select_related('user', 'institution')

# #     def list(self, request, *args, **kwargs):
# #         try:
# #             institution = Institution.objects.get(id=self.kwargs.get('institution_id'))
# #         except Institution.DoesNotExist:
# #             return Response(
# #                 {"error": "Institution not found"}, 
# #                 status=status.HTTP_404_NOT_FOUND
# #             )

# #         queryset = self.filter_queryset(self.get_queryset())
# #         page = self.paginate_queryset(queryset)

# #         if page is not None:
# #             serializer = self.get_serializer(page, many=True)
# #             return self.get_paginated_response(serializer.data)

# #         serializer = self.get_serializer(queryset, many=True)
# #         return Response({
# #             "institution": {
# #                 "id": institution.id,
# #                 "name": institution.name,
# #                 "code": institution.code,
# #             },
# #             "users": serializer.data
# #         })