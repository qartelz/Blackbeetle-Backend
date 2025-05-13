from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q, F
from ..users.models import User
from ..institutions.models import BaseModel
from datetime import timedelta
from django.db import transaction
from decimal import Decimal


def validate_positive_price(value):
    if value < Decimal('0'):
        raise ValidationError('Price must be non-negative')


def validate_positive_duration(value):
    if value <= 0:
        raise ValidationError('Duration must be positive')


class Plan(BaseModel):
    PLAN_TYPE_CHOICES = [
        ('B2B', 'Business'),
        ('B2C', 'Individual'),
    ]

    PLAN_TYPE = [
        ('BASIC', 'Basic'),
        ('PREMIUM', 'Premium'),
        ('SUPER_PREMIUM', 'Super Premium'),
    ]
    
    name = models.CharField(max_length=30,choices=PLAN_TYPE)
    plan_type = models.CharField(max_length=3, choices=PLAN_TYPE_CHOICES)
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[validate_positive_price]  # Fixed: Changed from validate_positive
    )
    duration_days = models.PositiveIntegerField(
        default=30,
        validators=[validate_positive_duration]  # Added validator
    )
    intended_users = models.CharField(max_length=255)
    index_coverage = models.JSONField(default=dict)
    stock_coverage = models.PositiveIntegerField()
    commodity_analysis = models.TextField(blank=True)
    client_interaction = models.CharField(max_length=255)
    webinars = models.CharField(max_length=255)
    portfolio_management = models.TextField(blank=True)
    code = models.CharField(max_length=50, unique=True)  # Added missing field referenced in index
    is_visible = models.BooleanField(default=True, db_index=True)

    def clean(self):
        super().clean()
        if self.duration_days < 1:
            raise ValidationError({'duration_days': 'Duration must be at least 1 day'})

    def __str__(self):
        return f"{self.name} ({self.get_plan_type_display()})"

    class Meta(BaseModel.Meta):
        ordering = ['plan_type', 'price']
        indexes = [
            models.Index(fields=['is_visible', 'plan_type', 'price']),
            models.Index(fields=['code']),
        ]


class Order(BaseModel):
    PAYMENT_TYPE_CHOICES = [
        ('OFFLINE', 'Offline Payment'),
        ('RAZORPAY', 'Razorpay Payment')
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded')
    ]

    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name='orders'
    )
    plan = models.ForeignKey(
        Plan, 
        on_delete=models.PROTECT,
        related_name='orders'
    )
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[validate_positive_price]
    )
    payment_type = models.CharField(
        max_length=20, 
        choices=PAYMENT_TYPE_CHOICES,
        default='RAZORPAY'
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES,
        default='PENDING',
        db_index=True
    )
    
    # Razorpay specific fields
    razorpay_order_id = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        unique=True
    )
    razorpay_payment_id = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        unique=True
    )
    razorpay_signature = models.CharField(
        max_length=500,
        blank=True,
        null=True
    )
    
    # Offline payment specific fields
    payment_reference = models.CharField(
        max_length=200, 
        blank=True,
        null=True,
        help_text="Reference number for offline payments"
    )
    payment_date = models.DateTimeField(null=True, blank=True)
    payment_notes = models.TextField(
        blank=True,
        null=True,
        max_length=1000
    )

    @transaction.atomic
    def complete_payment(self, **kwargs):
        """
        Generic payment completion method that handles both payment types
        """
        if self.status not in ['PENDING', 'PROCESSING']:  # Added PROCESSING state check
            raise ValidationError("Order is not in a valid state for completion")

        if self.payment_type == 'RAZORPAY':
            return self.complete_razorpay_payment(**kwargs)
        else:
            return self.complete_offline_payment(**kwargs)

    @transaction.atomic
    def complete_razorpay_payment(self, payment_id, signature):
        if self.payment_type != 'RAZORPAY':
            raise ValidationError("Invalid payment type for Razorpay completion")

        if Order.objects.filter(razorpay_payment_id=payment_id).exists():
            raise ValidationError("Payment ID already exists")

        self.razorpay_payment_id = payment_id
        self.razorpay_signature = signature
        self.status = 'COMPLETED'
        self.save()

        return self._create_or_extend_subscription()

    @transaction.atomic
    def complete_offline_payment(self, reference, payment_date=None, notes=None):
        if self.payment_type != 'OFFLINE':
            raise ValidationError("Invalid payment type for offline completion")

        payment_date = payment_date or timezone.now()
        if payment_date > timezone.now():
            raise ValidationError("Payment date cannot be in future")

        self.payment_reference = reference
        self.payment_date = payment_date
        self.payment_notes = notes
        self.status = 'COMPLETED'
        self.save()

        return self._create_or_extend_subscription()

    def _create_or_extend_subscription(self):
        """
        Creates a new subscription or extends existing one
        """
        now = timezone.now()
        
        with transaction.atomic():
            active_sub = Subscription.objects.filter(
                user=self.user,
                is_active=True,
                end_date__gt=now
            ).select_for_update().first()

            if active_sub and active_sub.plan == self.plan:
                # Extend existing subscription
                active_sub.end_date += timedelta(days=self.plan.duration_days)
                active_sub.save()
                return active_sub
            elif active_sub:
                # Deactivate old subscription if different plan
                active_sub.is_active = False
                active_sub.save()

            # Create new subscription with current date and time
            return Subscription.objects.create(
                user=self.user,
                plan=self.plan,
                order=self,
                start_date=now,  # Use current datetime
                end_date=now + timedelta(days=self.plan.duration_days),  # Use current datetime
                is_active=True
            )

    def clean(self):
        super().clean()
        if self.payment_date and self.payment_date > timezone.now():
            raise ValidationError("Payment date cannot be in the future")
        
        if self.amount != self.plan.price:
            raise ValidationError("Order amount must match plan price")

    def __str__(self):
        return f"Order {self.id} - {self.user.email} - {self.status}"

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=['status', 'payment_type']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['razorpay_order_id']),
            models.Index(fields=['razorpay_payment_id']),
        ]


class Subscription(BaseModel):
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name='subscriptions'
    )
    plan = models.ForeignKey(
        Plan, 
        on_delete=models.PROTECT,
        related_name='subscriptions'
    )
    order = models.ForeignKey(
        Order, 
        on_delete=models.PROTECT,
        related_name='subscriptions'
    )
    start_date = models.DateTimeField()  # Changed from DateField to DateTimeField
    end_date = models.DateTimeField()    # Changed from DateField to DateTimeField
    is_active = models.BooleanField(default=True)
    auto_renew = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(
        null=True,
        blank=True
    )

    def clean(self):
        super().clean()
        if self.end_date <= self.start_date:
            raise ValidationError("End date must be after start date")

    def is_valid(self):
        """
        Check if subscription is currently valid
        """
        now = timezone.now()
        return (
            self.is_active and
            not self.cancelled_at and
            self.start_date <= now <= self.end_date
        )

    def get_remaining_days(self):
        """
        Get remaining days in subscription
        """
        if not self.is_valid():
            return 0
        now = timezone.now()
        if now > self.end_date:
            return 0
        return (self.end_date - now).days

    def cancel(self):
        """
        Cancel the subscription
        """
        if not self.cancelled_at and self.is_valid():
            self.cancelled_at = timezone.now()
            self.auto_renew = False
            self.save()

    @transaction.atomic
    def save(self, *args, **kwargs):
        # Ensure only one active subscription per user
        if self.is_active:
            Subscription.objects.select_for_update().filter(
                user=self.user,
                is_active=True
            ).exclude(pk=self.pk).update(is_active=False)
        
        super().save(*args, **kwargs)

    def __str__(self):
        status = "Active" if self.is_valid() else "Inactive"
        return f"{self.user.email} - {self.plan.name} ({status})"

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=['is_active', 'start_date', 'end_date']),
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['end_date']),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(end_date__gt=F('start_date')),
                name='subscription_end_date_after_start_date'
            )
        ]