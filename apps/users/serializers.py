from rest_framework import serializers
from django.contrib.auth import authenticate
from ..users.models import User, LoginAttempt
from ..institutions.models import Institution, InstitutionUser
from ..subscriptions.models import Subscription,Plan
from django.utils import timezone
from django.db import transaction

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'phone_number', 'email', 'user_type', 'first_name', 'last_name', 'is_verified', 'date_of_birth', 'bio', 'last_login_ip', 'last_login_device']
        read_only_fields = ['id', 'user_type', 'is_verified', 'last_login_ip', 'last_login_device']

class LoginSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        phone_number = attrs.get('phone_number')
        password = attrs.get('password')

        if phone_number and password:
            user = authenticate(request=self.context.get('request'),
                                phone_number=phone_number, password=password)
            if not user:
                msg = 'Unable to log in with provided credentials.'
                raise serializers.ValidationError(msg, code='authorization')
        else:
            msg = 'Must include "phone_number" and "password".'
            raise serializers.ValidationError(msg, code='authorization')

        attrs['user'] = user
        return attrs

class TokenSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()

class B2CRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['phone_number', 'email', 'password', 'first_name', 'last_name']

    def create(self, validated_data):
        validated_data['user_type'] = User.UserType.B2C
        user = User.objects.create_user(**validated_data)
        return user

class B2BUserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    institution_code = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['phone_number', 'email', 'password', 'first_name', 'last_name', 'institution_code', 'date_of_birth', 'bio']

    def create(self, validated_data):
        institution_code = validated_data.pop('institution_code')
        institution = Institution.objects.get(code=institution_code)
        validated_data['user_type'] = User.UserType.B2B_USER
        user = User.objects.create_user(**validated_data)
        InstitutionUser.objects.create(user=user, institution=institution)
        return user

class B2BAdminRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    institution_name = serializers.CharField()
    institution_description = serializers.CharField(required=False)
    institution_website = serializers.URLField(required=False)
    institution_address = serializers.CharField(required=False)
    institution_contact_email = serializers.EmailField()
    institution_contact_phone = serializers.CharField()
    institution_max_users = serializers.IntegerField(required=False)

    class Meta:
        model = User
        fields = ['phone_number', 'email', 'password', 'first_name', 'last_name', 'date_of_birth', 'bio',
                  'institution_name', 'institution_description', 'institution_website', 'institution_address',
                  'institution_contact_email', 'institution_contact_phone', 'institution_max_users']

    def create(self, validated_data):
        institution_data = {
            'name': validated_data.pop('institution_name'),
            'description': validated_data.pop('institution_description', ''),
            'website': validated_data.pop('institution_website', ''),
            'address': validated_data.pop('institution_address', ''),
            'contact_email': validated_data.pop('institution_contact_email'),
            'contact_phone': validated_data.pop('institution_contact_phone'),
            'max_users': validated_data.pop('institution_max_users'),
        }
        validated_data['user_type'] = User.UserType.B2B_ADMIN
        with transaction.atomic(): 
            user = User.objects.create_user(**validated_data)
            Institution.objects.create(admin=user, **institution_data)
        return user

class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = ['id', 'name', 'code', 'description', 'website', 'address', 'contact_email', 'contact_phone', 'max_users']
        read_only_fields = ['id', 'code']

class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ['id', 'plan', 'start_date', 'end_date', 'is_active', 'auto_renew']
        read_only_fields = ['id']

class UserListSerializer(serializers.ModelSerializer):
    institution = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    subscription_detailes = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'phone_number', 
                 'user_type', 'is_active', 'institution', 'status', 'is_verified','subscription_detailes']

    def get_institution(self, obj):
        if obj.user_type in [User.UserType.B2B_ADMIN, User.UserType.B2B_USER]:
            if obj.user_type == User.UserType.B2B_ADMIN:
                institution = Institution.objects.filter(admin=obj).first()
            else:
                institution = InstitutionUser.objects.filter(user=obj).first()
                institution = institution.institution if institution else None
            
            return {
                'id': institution.id,
                'name': institution.name
            } if institution else None
        return None

    def get_status(self, obj):
        if obj.user_type in [User.UserType.B2B_ADMIN, User.UserType.B2B_USER]:
            institution_user = InstitutionUser.objects.filter(user=obj).first()
            if institution_user:
                return 'Active' if institution_user.is_active else 'Inactive'
        return 'Active' if obj.is_active else 'Inactive'
    def get_subscription_detailes(self, obj):
            if obj.user_type == User.UserType.B2B_USER:
                institution_user = InstitutionUser.objects.filter(user=obj).first()
                if institution_user:
                    subscriptions = Subscription.objects.filter(
                        user=obj,
                        is_active=True
                    ).select_related('plan', 'order')  # Optimize by selecting related fields
                    
                    if subscriptions.exists():
                        subscription_data = []
                        for subscription in subscriptions:
                            data = {
                                'id': subscription.id,
                                'start_date': subscription.start_date,
                                'end_date': subscription.end_date,
                                'is_active': subscription.is_active,
                                'auto_renew': subscription.auto_renew,
                                'plan': {
                                    'name': subscription.plan.name,
                                    'plan_type': subscription.plan.plan_type,
                                    'price': subscription.plan.price
                                },
                                'order': {
                                    'id': subscription.order.id,
                                    'amount': subscription.order.amount,
                                    'status': subscription.order.status,
                                    'payment_type': subscription.order.payment_type,
                                    'payment_date': subscription.order.payment_date
                                }
                            }
                            subscription_data.append(data)
                        return subscription_data
            return None

class UserActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'is_verified', 'is_active', 'user_type']
        read_only_fields = ['id', 'user_type']

class LoginAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAttempt
        fields = '__all__'




class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            'name',
        ]

class UserProfileSerializer(serializers.ModelSerializer):
    subscriptions = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    login_attempts = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'profile_picture',
            'full_name',
            'phone_number',
            'email',
            'city',
            'country',
            'subscriptions',
            'login_attempts',
            
        ]

   
    def get_full_name(self, obj):
    # Leverage the `get_full_name` method from the `User` model
        return obj.get_full_name()

    def get_subscriptions(self, obj):  # Fetch subscriptions with plan details
        subscriptions = Subscription.objects.filter(user=obj)
        return [
            {
                "plan": PlanSerializer(subscription.plan).data,  # Serialize the plan details
                "order": subscription.order.id,
                "start_date": subscription.start_date,
                "end_date": subscription.end_date,
                "is_active": subscription.is_active,
                
            }
            for subscription in subscriptions
        ]
    def get_login_attempts(self, obj):
        # Fetch last 1 login attempts for the user
        login_attempts = LoginAttempt.objects.filter(user=obj).order_by('-timestamp')[:1]
        
        if not login_attempts.exists():
            return []
            
        return [
            {
                "ip_address": attempt.ip_address,
                "login_time": attempt.timestamp,
                "success": attempt.success,
                "user_agent": attempt.user_agent,
                "device_type": attempt.device_type,
                "browser": attempt.browser,
                "os": attempt.os,
                "country": attempt.country,
                "city": attempt.city,
                "region": attempt.region,
                "timestamp": str(attempt.timestamp)
            }
            for attempt in login_attempts
        ]

class UserProfileEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['profile_picture', 'first_name','last_name', 'email', 'city','country']



    def validate_email(self, value):
        """Ensure email is unique except for the current user."""
        user = self.instance
        if User.objects.exclude(id=user.id).filter(email=value).exists():
            raise serializers.ValidationError("This email is already in use.")
        return value
    


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ['name']


class UserProfileSerializer(serializers.ModelSerializer):
    subscriptions = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
   

    class Meta:
        model = User
        fields = [
            'profile_picture',
            'full_name',
            'phone_number',
            'email',
            'city',
            'country',
            'subscriptions',
        ]

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_subscriptions(self, obj):
        now = timezone.now().date()
        last_expired = (
            Subscription.objects
            .filter(user=obj, end_date__lt=now)
            .order_by('-end_date')
            .first()
        )
        if not last_expired:
            return []

        return [{
            "plan": PlanSerializer(last_expired.plan).data,
            "order": last_expired.order.id,
            "start_date": last_expired.start_date,
            "end_date": last_expired.end_date,
            "is_active": last_expired.is_active,
        }]
