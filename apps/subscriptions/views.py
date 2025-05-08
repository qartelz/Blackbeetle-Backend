from rest_framework import status, views,generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.throttling import UserRateThrottle
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Plan, Order, Subscription
from .serializers import (
    PlanSerializer, OrderReadSerializer, OrderWriteSerializer,
    SubscriptionSerializer, CompleteRazorpayPaymentSerializer,
    CompleteOfflinePaymentSerializer,AdminOrderCreateSerializer,AdminOfflinePaymentSerializer,
)
from django_filters import rest_framework as filters

from .admin_serializers import (
    AdminOrderCreateSerializer,
    AdminOfflinePaymentSerializer,
    AdminOrderWriteSerializer,
    AdminPlanSerializer,
    AdminSubscriptionSerializer,
    AdminInstitutionSerializer,
    AdminUserSerializer,
    AdminOrderReadSerializer,
    AdminOrderDetailedReadSerializer

)
from ..institutions.models import Institution
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import get_user_model
from .razorpay_utils import (
    create_razorpay_order, verify_razorpay_payment_signature
)
from rest_framework.generics import GenericAPIView
import logging
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q

logger = logging.getLogger(__name__)

User = get_user_model()



class BaseAPIView(GenericAPIView): 
    throttle_classes = [UserRateThrottle]

class PlanListCreateView(BaseAPIView):
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['plan_type', 'duration_days','name']
    ordering_fields = ['price', 'duration_days']
    queryset = Plan.objects.all()  # Required for GenericAPIView
    serializer_class = PlanSerializer  # Required for GenericAPIView

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get(self, request):
        """List all visible plans based on user type"""
        try:
            user = request.user
            if user.is_staff:
                queryset = Plan.objects.all()
            elif user.user_type in [User.UserType.B2B_ADMIN, User.UserType.B2B_USER]:
                queryset = Plan.objects.filter(is_visible=True, plan_type='B2B')
            else:  # B2C user
                queryset = Plan.objects.filter(is_visible=True, plan_type='B2C')

            # Apply the filters and ordering
            queryset = self.filter_queryset(queryset)
            
            serializer = PlanSerializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error fetching plans: {str(e)}")
            return Response(
                {'error': 'Failed to fetch plans'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @transaction.atomic
    def post(self, request):
        """Create a new plan (admin only)"""
        try:
            serializer = PlanSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error creating plan: {str(e)}")
            return Response(
                {'error': 'Failed to create plan'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PlanDetailView(BaseAPIView):
    # def get_permissions(self):
    #     if self.request.method in ['PUT', 'DELETE']:
    #         return [IsAdminUser()]
    #     return [IsAuthenticated()]

    def get(self, request, pk):
        """Retrieve plan details"""
        try:
            plan = get_object_or_404(Plan, pk=pk)
            if not plan.is_visible and not request.user.is_staff:
                return Response(
                    {'error': 'Plan not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            serializer = PlanSerializer(plan)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error fetching plan {pk}: {str(e)}")
            return Response(
                {'error': 'Failed to fetch plan'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @transaction.atomic
    def put(self, request, pk):
        """Update plan details (admin only)"""
        try:
            plan = get_object_or_404(Plan, pk=pk)
            serializer = PlanSerializer(plan, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error updating plan {pk}: {str(e)}")
            return Response(
                {'error': 'Failed to update plan'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @transaction.atomic
    def delete(self, request, pk):
        """Delete plan (admin only)"""
        try:
            plan = get_object_or_404(Plan, pk=pk)
            if plan.subscriptions.filter(is_active=True).exists():
                return Response(
                    {'error': 'Cannot delete plan with active subscriptions'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            plan.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error deleting plan {pk}: {str(e)}")
            return Response(
                {'error': 'Failed to delete plan'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class OrderListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List user's orders"""
        try:
            orders = Order.objects.filter(user=request.user).order_by('-created_at')
            serializer = OrderReadSerializer(orders, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error fetching orders: {str(e)}")
            return Response(
                {'error': 'Failed to fetch orders'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @transaction.atomic
    def post(self, request):
        """Create a new order"""
        try:
            serializer = OrderWriteSerializer(
                data=request.data,
                context={'request': request}
            )
            if serializer.is_valid():
                order = serializer.save()
                
                if order.payment_type == 'RAZORPAY':
                    razorpay_order = create_razorpay_order(order)
                    response_data = OrderReadSerializer(order).data
                    response_data['razorpay_order'] = {
                        'id': razorpay_order['id'],
                        'amount': razorpay_order['amount'],
                        'currency': razorpay_order['currency']
                    }
                    return Response(response_data, status=status.HTTP_201_CREATED)
                
                return Response(
                    OrderReadSerializer(order).data,
                    status=status.HTTP_201_CREATED
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error creating order: {str(e)}")
            return Response(
                {'error': 'Failed to create order'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class OrderDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        """Retrieve order details"""
        try:
            order = get_object_or_404(Order, pk=pk, user=request.user)
            serializer = OrderReadSerializer(order)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error fetching order {pk}: {str(e)}")
            return Response(
                {'error': 'Failed to fetch order'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @transaction.atomic
    def delete(self, request, pk):
        """Cancel pending order"""
        try:
            order = get_object_or_404(Order, pk=pk, user=request.user)
            if order.status not in ['PENDING', 'PROCESSING']:
                return Response(
                    {'error': 'Only pending or processing orders can be cancelled'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            order.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error cancelling order {pk}: {str(e)}")
            return Response(
                {'error': 'Failed to cancel order'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CompleteRazorpayPaymentView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        """Complete Razorpay payment"""
        try:
            order = get_object_or_404(
                Order,
                pk=pk,
                user=request.user,
                payment_type='RAZORPAY'
            )
            
            if order.status not in ['PENDING', 'PROCESSING']:
                return Response(
                    {'error': 'Invalid order status'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = CompleteRazorpayPaymentSerializer(data=request.data)
            if serializer.is_valid():
                # Verify payment signature
                if not verify_razorpay_payment_signature(
                    serializer.validated_data['razorpay_payment_id'],
                    order.razorpay_order_id,
                    serializer.validated_data['razorpay_signature']
                ):
                    return Response(
                        {'error': 'Invalid payment signature'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Complete payment and create subscription
                subscription = order.complete_razorpay_payment(
                    payment_id=serializer.validated_data['razorpay_payment_id'],
                    signature=serializer.validated_data['razorpay_signature']
                )
                
                return Response(
                    SubscriptionSerializer(subscription).data,
                    status=status.HTTP_200_OK
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error completing Razorpay payment for order {pk}: {str(e)}")
            return Response(
                {'error': 'Failed to complete payment'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CompleteOfflinePaymentView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        """Complete offline payment"""
        try:
            order = get_object_or_404(
                Order,
                pk=pk,
                user=request.user,
                payment_type='OFFLINE'
            )
            
            if order.status not in ['PENDING', 'PROCESSING']:
                return Response(
                    {'error': 'Invalid order status'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = CompleteOfflinePaymentSerializer(data=request.data)
            if serializer.is_valid():
                subscription = order.complete_offline_payment(
                    reference=serializer.validated_data['payment_reference'],
                    payment_date=serializer.validated_data.get('payment_date'),
                    notes=serializer.validated_data.get('payment_notes')
                )
                return Response(
                    SubscriptionSerializer(subscription).data,
                    status=status.HTTP_200_OK
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error completing offline payment for order {pk}: {str(e)}")
            return Response(
                {'error': 'Failed to complete payment'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class SubscriptionListView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List user's subscriptions"""
        try:
            subscriptions = Subscription.objects.filter(
                user=request.user
            ).order_by('-created_at')
            serializer = SubscriptionSerializer(subscriptions, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error fetching subscriptions: {str(e)}")
            return Response(
                {'error': 'Failed to fetch subscriptions'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class SubscriptionDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        """Retrieve subscription details"""
        try:
            subscription = get_object_or_404(
                Subscription,
                pk=pk,
                user=request.user
            )
            serializer = SubscriptionSerializer(subscription)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error fetching subscription {pk}: {str(e)}")
            return Response(
                {'error': 'Failed to fetch subscription'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CancelSubscriptionView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        """Cancel an active subscription"""
        try:
            subscription = get_object_or_404(
                Subscription,
                pk=pk,
                user=request.user,
                is_active=True
            )
            
            if subscription.cancelled_at:
                return Response(
                    {'error': 'Subscription is already cancelled'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            subscription.cancel()
            return Response(
                SubscriptionSerializer(subscription).data,
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error cancelling subscription {pk}: {str(e)}")
            return Response(
                {'error': 'Failed to cancel subscription'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



# class AdminOrderCreateView(BaseAPIView):
#     permission_classes = [IsAdminUser]

#     def get(self, request):
#         """List all orders (admin only)"""
#         try:
#             orders = Order.objects.all().order_by('-created_at')
#             serializer = OrderReadSerializer(orders, many=True)
#             return Response(serializer.data)
#         except Exception as e:
#             logger.error(f"Error fetching orders: {str(e)}")
#             return Response(
#                 {'error': 'Failed to fetch orders'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )   


#     @transaction.atomic
#     def post(self, request):
#         """Create a new order for B2B user (admin only)"""
#         try:
#             serializer = AdminOrderCreateSerializer(data=request.data)
#             if serializer.is_valid():
#                 order = serializer.save()
#                 return Response(
#                     OrderReadSerializer(order).data,
#                     status=status.HTTP_201_CREATED
#                 )
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#         except Exception as e:
#             logger.error(f"Error creating admin order: {str(e)}")
#             return Response(
#                 {'error': 'Failed to create order'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

# class AdminCompleteOfflinePaymentView(BaseAPIView):
#     permission_classes = [IsAdminUser]

#     @transaction.atomic
#     def post(self, request, pk):
#         """Complete offline payment for B2B user (admin only)"""
#         try:
#             order = get_object_or_404(Order, pk=pk, payment_type='OFFLINE')
            
#             if order.status not in ['PENDING', 'PROCESSING']:
#                 return Response(
#                     {'error': 'Invalid order status'},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )

#             serializer = AdminOfflinePaymentSerializer(data=request.data)
#             if serializer.is_valid():
#                 subscription = order.complete_offline_payment(
#                     reference=serializer.validated_data['payment_reference'],
#                     payment_date=serializer.validated_data.get('payment_date'),
#                     notes=serializer.validated_data.get('payment_notes')
#                 )
#                 return Response(
#                     SubscriptionSerializer(subscription).data,
#                     status=status.HTTP_200_OK
#                 )
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#         except ValidationError as e:
#             return Response(
#                 {'error': str(e)},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
#         except Exception as e:
#             logger.error(f"Error completing admin offline payment for order {pk}: {str(e)}")
#             return Response(
#                 {'error': 'Failed to complete payment'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )


# class AdminOrderCreateView(views.APIView):
#     permission_classes = [IsAdminUser]

#     def get(self, request):
#         orders = Order.objects.all().order_by('-created_at')
#         serializer = AdminOrderReadSerializer(orders, many=True)
#         return Response(serializer.data)

#     def post(self, request):
#         serializer = AdminOrderCreateSerializer(data=request.data)
#         if serializer.is_valid():
#             order = serializer.save()
#             return Response(AdminOrderReadSerializer(order).data, status=status.HTTP_201_CREATED)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# class AdminCompleteOfflinePaymentView(BaseAPIView):
#     permission_classes = [IsAdminUser]

#     @transaction.atomic
#     def post(self, request, pk):
#         try:
#             order = get_object_or_404(Order, pk=pk, payment_type='OFFLINE')
            
#             if order.status not in ['PENDING', 'PROCESSING']:
#                 return Response(
#                     {'error': 'Invalid order status'},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )

#             serializer = AdminOfflinePaymentSerializer(data=request.data)
#             if serializer.is_valid():
#                 subscription = order.complete_offline_payment(
#                     reference=serializer.validated_data['payment_reference'],
#                     payment_date=serializer.validated_data.get('payment_date'),
#                     notes=serializer.validated_data.get('payment_notes')
#                 )
#                 return Response(
#                     AdminSubscriptionSerializer(subscription).data,
#                     status=status.HTTP_200_OK
#                 )
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#         except ValidationError as e:
#             return Response(
#                 {'error': str(e)},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
#         except Exception as e:
#             logger.error(f"Error completing admin offline payment for order {pk}: {str(e)}")
#             return Response(
#                 {'error': 'Failed to complete payment'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )



class OrderPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class OrderFilter(filters.FilterSet):
    start_date = filters.DateFilter(field_name='created_at', lookup_expr='gte')
    end_date = filters.DateFilter(field_name='created_at', lookup_expr='lte')
    status = filters.ChoiceFilter(choices=Order.STATUS_CHOICES)
    payment_type = filters.ChoiceFilter(choices=Order.PAYMENT_TYPE_CHOICES)
    user_email = filters.CharFilter(field_name='user__email', lookup_expr='icontains')
    min_amount = filters.NumberFilter(field_name='amount', lookup_expr='gte')
    max_amount = filters.NumberFilter(field_name='amount', lookup_expr='lte')
    plan = filters.NumberFilter(field_name='plan__id')

    class Meta:
        model = Order
        fields = ['status', 'payment_type', 'user_email', 'plan']

class AdminOrderListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    pagination_class = OrderPagination
    filterset_class = OrderFilter
    
    def get_queryset(self):
        return Order.objects.select_related(
            'user', 'plan'
        ).prefetch_related(
            'subscriptions'
        ).order_by('-created_at')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AdminOrderCreateSerializer
        return AdminOrderReadSerializer

class AdminOrderDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminOrderDetailedReadSerializer
    lookup_field = 'id'

    def get_queryset(self):
        return Order.objects.select_related(
            'user',
            'plan',
            'user__subscriptions',  # Add prefetch for subscriptions
        ).prefetch_related(
            'subscriptions',
            'plan__subscriptions'
        )

    def delete(self, request, *args, **kwargs):
        order = self.get_object()
        if order.status not in ['PENDING', 'PROCESSING']:
            return Response(
                {"detail": "Only pending or processing orders can be cancelled"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.status = 'FAILED'
        order.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

class AdminOrderOfflinePaymentView(views.APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, payment_type='OFFLINE')
        serializer = AdminOfflinePaymentSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                subscription = order.complete_offline_payment(
                    reference=serializer.validated_data['payment_reference'],
                    payment_date=serializer.validated_data.get('payment_date'),
                    notes=serializer.validated_data.get('payment_notes')
                )
                return Response(
                    AdminSubscriptionSerializer(subscription).data,
                    status=status.HTTP_200_OK
                )
            except ValidationError as e:
                return Response(
                    {'detail': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class InstitutionListView(generics.ListAPIView):
    serializer_class = AdminInstitutionSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = Institution.objects.all()
        search_query = self.request.query_params.get('search', None)
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) | Q(code__icontains=search_query)
            )
        return queryset

class InstitutionUsersView(generics.ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        institution_id = self.kwargs['institution_id']
        queryset = User.objects.filter(
            institution_memberships__institution_id=institution_id,
            user_type__in=[User.UserType.B2B_USER]
        )
        search_query = self.request.query_params.get('search', None)
        if search_query:
            queryset = queryset.filter(
                Q(email__icontains=search_query) | Q(phone_number__icontains=search_query)
            )
        return queryset

class AvailableB2BPlansView(generics.ListAPIView):
    serializer_class = AdminPlanSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return Plan.objects.filter(plan_type='B2B', is_visible=True)




"""
this is new free trail for the user provided by the admin created by sidharth before testing
"""



class GrantFreeTrialView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        # Check if user already got a trial
        if user.subscriptions.filter(plan__is_trial=True).exists():
            return Response({"error": "User has already received a free trial"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            trial_plan = Plan.objects.get(is_trial=True)  # Make sure your Plan model has `is_trial` boolean field
        except Plan.DoesNotExist:
            return Response({"error": "Free Trial plan not found"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Create a zero-amount order for trial
        order = Order.objects.create(
            user=user,
            plan=trial_plan,
            amount=0,
            payment_type='OFFLINE',  # Marking it as offline since it's a manual trigger
            status='COMPLETED',
            payment_reference='FREE_TRIAL',
            payment_date=timezone.now()
        )

        # Create subscription using existing method
        subscription = order._create_or_extend_subscription()

        return Response({
            "message": "Free trial granted",
            "subscription_id": subscription.id,
            "start_date": subscription.start_date,
            "end_date": subscription.end_date
        }, status=status.HTTP_200_OK)
