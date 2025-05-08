# from rest_framework import serializers
# from ..users.models import User
# from .models import Institution, InstitutionUser

# class InstitutionListSerializer(serializers.ModelSerializer):
#     admin_count = serializers.SerializerMethodField()
#     user_count = serializers.SerializerMethodField()

#     class Meta:
#         model = Institution
#         fields = ['id', 'name', 'code', 'admin_count', 'user_count', 'is_active', 'created_at']

#     def get_admin_count(self, obj):
#         return User.objects.filter(
#             user_type=User.UserType.B2B_ADMIN,
#             administered_institution=obj
#         ).count()

#     def get_user_count(self, obj):
#         return obj.users.filter(is_active=True).count()

# class InstitutionDetailSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Institution
#         fields = [
#             'id', 'name', 'code', 'description', 'website', 
#             'address', 'contact_email', 'contact_phone', 
#             'max_users', 'is_active', 'created_at'
#         ]

# class InstitutionUserListSerializer(serializers.ModelSerializer):
#     user = serializers.SerializerMethodField()
#     email = serializers.EmailField(source='user.email')
#     user_type = serializers.CharField(source='user.user_type')
    
#     class Meta:
#         model = InstitutionUser
#         fields = ['id', 'user', 'email', 'user_type', 'role', 'is_active', 'code', 'join_date']

#     def get_user(self, obj):
#         return {
#             'id': obj.user.id,
#             'first_name': obj.user.first_name,
#             'last_name': obj.user.last_name,
#             'phone_number': str(obj.user.phone_number),
#             'is_verified': obj.user.is_verified
#         }

from rest_framework import serializers
from .models import Institution, InstitutionUser
from ..users.models import User

class InstitutionListSerializer(serializers.ModelSerializer):
    admin = serializers.SerializerMethodField()
    active_users = serializers.SerializerMethodField()

    class Meta:
        model = Institution
        fields = ['id', 'name', 'code', 'website', 'contact_email', 'contact_phone', 'max_users', 'active_users', 'is_active', 'admin']

    def get_admin(self, obj):
        if obj.admin:
            return {
                'name': f"{obj.admin.first_name} {obj.admin.last_name}",
                'email': obj.admin.email
            }
        return None

    def get_active_users(self, obj):
        return obj.users.filter(is_active=True).count()

class InstitutionDetailSerializer(serializers.ModelSerializer):
    admin = serializers.SerializerMethodField()
    active_users = serializers.SerializerMethodField()

    class Meta:
        model = Institution
        fields = ['id', 'name', 'code', 'description', 'website', 'address', 'contact_email', 'contact_phone', 'max_users', 'active_users', 'is_active', 'created_at', 'admin']

    def get_admin(self, obj):
        if obj.admin:
            return {
                'name': f"{obj.admin.first_name} {obj.admin.last_name}",
                'email': obj.admin.email
            }
        return None

    def get_active_users(self, obj):
        return obj.users.filter(is_active=True).count()

class InstitutionUserListSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    
    class Meta:
        model = InstitutionUser
        fields = ['id', 'user', 'role', 'is_active', 'code', 'join_date']

    def get_user(self, obj):
        return {
            'id': obj.user.id,
            'first_name': obj.user.first_name,
            'last_name': obj.user.last_name,
            'email': obj.user.email,
            'phone_number': str(obj.user.phone_number),
            'is_verified': obj.user.is_verified,
            'is_blocked': not obj.user.is_active
        }



class B2BUserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    role = serializers.CharField(required=False, default="MEMBER")

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number', 
                 'password', 'confirm_password', 'role', 'date_of_birth', 'bio']

    def validate(self, data):
        if data['password'] != data.pop('confirm_password'):
            raise serializers.ValidationError("Passwords do not match")
        return data

class B2BUserUpdateSerializer(serializers.ModelSerializer):
    role = serializers.CharField(required=False)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'date_of_birth', 'bio']
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': False},
            'email': {'required': False}
        }

class B2BUserDetailSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    institution = serializers.SerializerMethodField()
    join_date = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'phone_number',
                 'is_active', 'role', 'institution', 'join_date', 
                 'date_of_birth', 'bio', 'created_at']

    def get_role(self, obj):
        institution_user = obj.institution_memberships.first()
        return institution_user.role if institution_user else None

    def get_institution(self, obj):
        institution_user = obj.institution_memberships.first()
        if institution_user:
            return {
                'id': institution_user.institution.id,
                'name': institution_user.institution.name,
                'code': institution_user.institution.code
            }
        return None

    def get_join_date(self, obj):
        institution_user = obj.institution_memberships.first()
        return institution_user.join_date if institution_user else None