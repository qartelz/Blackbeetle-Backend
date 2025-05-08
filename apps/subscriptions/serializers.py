# serializers.py
from rest_framework import serializers
from django.utils import timezone
from .models import Plan, Order, Subscription
from django.contrib.auth import get_user_model

User = get_user_model()

class PlanSerializer(serializers.ModelSerializer):
    total_active_subscriptions = serializers.SerializerMethodField()
    duration_display = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = [
            'id', 'name', 'plan_type', 'price', 'duration_days',
            'intended_users', 'index_coverage', 'stock_coverage',
            'commodity_analysis', 'client_interaction', 'webinars',
            'portfolio_management', 'code', 'is_visible',
            'total_active_subscriptions', 'duration_display',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_total_active_subscriptions(self, obj):
        return obj.subscriptions.filter(
            is_active=True,
            end_date__gte=timezone.now().date()
        ).count()

    def get_duration_display(self, obj):
        if obj.duration_days == 30:
            return "Monthly"
        elif obj.duration_days == 365:
            return "Annual"
        return f"{obj.duration_days} days"

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero")
        return value

    def validate_duration_days(self, value):
        if value <= 0:
            raise serializers.ValidationError("Duration must be greater than zero")
        return value

class OrderReadSerializer(serializers.ModelSerializer):
    plan_details = PlanSerializer(source='plan', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    payment_status_display = serializers.CharField(source='get_status_display', read_only=True)
    can_be_cancelled = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'user_email', 'plan', 'plan_details',
            'amount', 'payment_type', 'status', 'payment_status_display',
            'razorpay_order_id', 'razorpay_payment_id', 
            'razorpay_signature', 'payment_reference', 'payment_date',
            'payment_notes', 'can_be_cancelled', 'created_at', 'updated_at'
        ]
        read_only_fields = fields

    def get_can_be_cancelled(self, obj):
        return obj.status in ['PENDING', 'PROCESSING']

class OrderWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['plan', 'payment_type']

    def validate(self, data):
        plan = data.get('plan')
        user = self.context['request'].user

        # Validate plan is visible
        if not plan.is_visible:
            raise serializers.ValidationError({"plan": "This plan is not available"})

        # Check for existing active subscription
        active_subscription = Subscription.objects.filter(
            user=user,
            plan=plan,
            is_active=True,
            end_date__gte=timezone.now().date()
        ).exists()

        if active_subscription:
            raise serializers.ValidationError(
                {"plan": "You already have an active subscription to this plan"}
            )

        # Check for pending orders
        pending_order = Order.objects.filter(
            user=user,
            status__in=['PENDING', 'PROCESSING']
        ).exists()

        if pending_order:
            raise serializers.ValidationError(
                {"non_field_errors": "You have a pending order. Please complete or cancel it first"}
            )

        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        validated_data['amount'] = validated_data['plan'].price
        return super().create(validated_data)

class SubscriptionSerializer(serializers.ModelSerializer):
    plan_details = PlanSerializer(source='plan', read_only=True)
    order_details = OrderReadSerializer(source='order', read_only=True)
    status = serializers.SerializerMethodField()
    remaining_days = serializers.SerializerMethodField()
    
    class Meta:
        model = Subscription
        fields = [
            'id', 'user', 'plan', 'plan_details', 'order', 'order_details',
            'start_date', 'end_date', 'is_active', 'status', 
            'remaining_days', 'auto_renew', 'cancelled_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields

    def get_status(self, obj):
        today = timezone.now().date()
        
        if obj.cancelled_at:
            return "Cancelled"
        elif not obj.is_active:
            return "Inactive"
        elif obj.end_date < today:
            return "Expired"
        elif obj.start_date > today:
            return "Scheduled"
        else:
            return "Active"

    def get_remaining_days(self, obj):
        return obj.get_remaining_days()

class CompleteRazorpayPaymentSerializer(serializers.Serializer):
    razorpay_payment_id = serializers.CharField()
    razorpay_signature = serializers.CharField()
    
    def validate_razorpay_payment_id(self, value):
        if not value.startswith('pay_'):
            raise serializers.ValidationError("Invalid Razorpay payment ID format")
        
        # Check if payment ID is already used
        if Order.objects.filter(razorpay_payment_id=value).exists():
            raise serializers.ValidationError("Payment already processed")
            
        return value

class CompleteOfflinePaymentSerializer(serializers.Serializer):
    payment_reference = serializers.CharField(max_length=200)
    payment_date = serializers.DateTimeField(required=False)
    payment_notes = serializers.CharField(required=False, allow_blank=True)

    def validate_payment_reference(self, value):
        if Order.objects.filter(payment_reference=value).exists():
            raise serializers.ValidationError("Payment reference already exists")
        return value

    def validate_payment_date(self, value):
        if value and value > timezone.now():
            raise serializers.ValidationError("Payment date cannot be in the future")
        return value
    


class AdminOrderCreateSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField()
    plan_id = serializers.IntegerField()

    class Meta:
        model = Order
        fields = ['user_id', 'plan_id', 'payment_type']

    def validate_user_id(self, value):
        try:
            print(value,"-----------------------------------------")
            user = User.objects.get(id=value)
            if user.user_type not in [User.UserType.B2B_ADMIN, User.UserType.B2B_USER]:
                raise serializers.ValidationError("User must be a B2B user")
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid user ID")
        return value

    def validate_plan_id(self, value):
        try:
            plan = Plan.objects.get(id=value)
            if plan.plan_type != 'B2B':
                raise serializers.ValidationError("Plan must be a B2B plan")
        except Plan.DoesNotExist:
            raise serializers.ValidationError("Invalid plan ID")
        return value

    def create(self, validated_data):
        user = User.objects.get(id=validated_data['user_id'])
        plan = Plan.objects.get(id=validated_data['plan_id'])
        return Order.objects.create(
            user=user,
            plan=plan,
            amount=plan.price,
            payment_type=validated_data['payment_type']
        )

class AdminOfflinePaymentSerializer(serializers.Serializer):
    payment_reference = serializers.CharField(max_length=200)
    payment_date = serializers.DateTimeField(required=False)
    payment_notes = serializers.CharField(required=False, allow_blank=True)

    def validate_payment_reference(self, value):
        if Order.objects.filter(payment_reference=value).exists():
            raise serializers.ValidationError("Payment reference already exists")
        return value

    def validate_payment_date(self, value):
        if value and value > timezone.now():
            raise serializers.ValidationError("Payment date cannot be in the future")
        return value

