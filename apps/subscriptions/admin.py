from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.urls import reverse
from django.db.models import Count
from decimal import Decimal
from .models import Plan, Order, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'plan_type',
        'price',
        'duration_days',
        'is_visible',
        'active_subscriptions_count',
        'total_orders'
    ]
    list_filter = ['plan_type', 'is_visible', 'duration_days']
    search_fields = ['name', 'code', 'intended_users']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = [
        (None, {
            'fields': ('name', 'plan_type', 'code', 'is_visible')
        }),
        ('Pricing & Duration', {
            'fields': ('price', 'duration_days')
        }),
        ('Features', {
            'fields': (
                'intended_users',
                'index_coverage',
                'stock_coverage',
                'commodity_analysis',
                'client_interaction',
                'webinars',
                'portfolio_management'
            )
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    ]

    def active_subscriptions_count(self, obj):
        return obj.subscriptions.filter(
            is_active=True,
            end_date__gte=timezone.now().date()
        ).count()
    active_subscriptions_count.short_description = 'Active Subs'

    def total_orders(self, obj):
        return obj.orders.count()
    total_orders.short_description = 'Total Orders'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'user_email',
        'plan_name',
        'amount',
        'payment_type',
        'status',
        'created_at',
        'payment_reference_display'
    ]
    list_filter = ['status', 'payment_type', 'created_at']
    search_fields = [
        'user__email',
        'razorpay_order_id',
        'razorpay_payment_id',
        'payment_reference'
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
        'razorpay_order_id',
        'razorpay_payment_id',
        'razorpay_signature'
    ]
    actions = ['mark_as_completed', 'mark_as_failed', 'mark_as_refunded']
    
    fieldsets = [
        (None, {
            'fields': ('user', 'plan', 'amount', 'payment_type', 'status')
        }),
        ('Razorpay Details', {
            'fields': (
                'razorpay_order_id',
                'razorpay_payment_id',
                'razorpay_signature'
            ),
            'classes': ('collapse',),
            'description': 'Razorpay payment details'
        }),
        ('Offline Payment Details', {
            'fields': (
                'payment_reference',
                'payment_date',
                'payment_notes'
            ),
            'classes': ('collapse',),
            'description': 'Offline payment details'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    ]

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
    
    def plan_name(self, obj):
        return obj.plan.name
    plan_name.short_description = 'Plan'

    def payment_reference_display(self, obj):
        if obj.payment_type == 'RAZORPAY':
            return obj.razorpay_payment_id or '-'
        return obj.payment_reference or '-'
    payment_reference_display.short_description = 'Reference'

    @admin.action(description='Mark selected orders as completed')
    def mark_as_completed(self, request, queryset):
        updated = queryset.filter(status='PENDING').update(status='COMPLETED')
        self.message_user(request, f'{updated} orders were marked as completed.')

    @admin.action(description='Mark selected orders as failed')
    def mark_as_failed(self, request, queryset):
        updated = queryset.filter(status='PENDING').update(status='FAILED')
        self.message_user(request, f'{updated} orders were marked as failed.')

    @admin.action(description='Mark selected orders as refunded')
    def mark_as_refunded(self, request, queryset):
        updated = queryset.filter(status='COMPLETED').update(status='REFUNDED')
        self.message_user(request, f'{updated} orders were marked as refunded.')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'user_email',
        'plan_name',
        'status_badge',
        'start_date',
        'end_date',
        'remaining_days',
        'auto_renew'
    ]
    list_filter = [
        'is_active',
        'auto_renew',
        'start_date',
        'end_date',
        'cancelled_at'
    ]
    search_fields = ['user__email', 'plan__name']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['cancel_subscriptions', 'enable_auto_renew', 'disable_auto_renew']
    
    fieldsets = [
        (None, {
            'fields': ('user', 'plan', 'order')
        }),
        ('Subscription Details', {
            'fields': (
                'start_date',
                'end_date',
                'is_active',
                'auto_renew',
                'cancelled_at'
            )
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    ]

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
    
    def plan_name(self, obj):
        return obj.plan.name
    plan_name.short_description = 'Plan'

    def remaining_days(self, obj):
        days = obj.get_remaining_days()
        return f"{days} days"
    remaining_days.short_description = 'Remaining'

    def status_badge(self, obj):
        if obj.is_valid():
            color = 'green'
            text = 'Active'
        else:
            color = 'red'
            text = 'Inactive'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            text
        )
    status_badge.short_description = 'Status'

    @admin.action(description='Cancel selected subscriptions')
    def cancel_subscriptions(self, request, queryset):
        for subscription in queryset.filter(cancelled_at__isnull=True):
            subscription.cancel()
        self.message_user(request, 'Selected subscriptions have been cancelled.')

    @admin.action(description='Enable auto-renew')
    def enable_auto_renew(self, request, queryset):
        updated = queryset.filter(is_active=True).update(auto_renew=True)
        self.message_user(request, f'Auto-renew enabled for {updated} subscriptions.')

    @admin.action(description='Disable auto-renew')
    def disable_auto_renew(self, request, queryset):
        updated = queryset.update(auto_renew=False)
        self.message_user(request, f'Auto-renew disabled for {updated} subscriptions.')