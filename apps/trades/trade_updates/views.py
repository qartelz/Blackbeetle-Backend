from django.http import StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from asgiref.sync import sync_to_async
import json
import asyncio
from datetime import datetime
from django.utils import timezone
from apps.subscriptions.models import Subscription
from apps.indexAndCommodity.models import IndexAndCommodity
from ..serializers.tradeconsumer_serializers import IndexAndCommoditySeraializer, CompanySerializer
from ..models import Company
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

class TradeUpdatesSSE(APIView):
    authentication_classes = [JWTAuthentication]

    async def get_active_subscription(self, user):
        return await sync_to_async(Subscription.objects.filter)(
            user=user,
            is_active=True,
            start_date__lte=timezone.now().date(),
            end_date__gte=timezone.now().date()
        ).select_related('plan').get()

    async def get_all_data(self, user, subscription):
        plan_type = subscription.plan.name
        plan_filters = {
            'BASIC': ['BASIC'],
            'PREMIUM': ['BASIC', 'PREMIUM'],
            'SUPER_PREMIUM': ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
        }
        allowed_plans = plan_filters.get(plan_type, [])

        # Apply filters to Trades App Data
        companies = await sync_to_async(list)(Company.objects.filter(
            trades__status="ACTIVE",
            trades__created_at__date__gte=subscription.start_date,
            trades__created_at__date__lte=subscription.end_date,
            trades__plan_type__in=allowed_plans
        ).prefetch_related('trades'))

        index_companies = await sync_to_async(list)(IndexAndCommodity.objects.filter(
            trades__status="ACTIVE",
            trades__created_at__date__gte=subscription.start_date,
            trades__created_at__date__lte=subscription.end_date,
            trades__plan_type__in=allowed_plans
        ).prefetch_related('trades'))

        return {
            'stock_data': await sync_to_async(CompanySerializer)(companies, many=True).data,
            'index_data': await sync_to_async(IndexAndCommoditySeraializer)(index_companies, many=True).data
        }

    async def generate_events(self, request):
        try:
            # Initial data
            subscription = await self.get_active_subscription(request.user)
            data = await self.get_all_data(request.user, subscription)

            # Send initial data
            yield f"data: {json.dumps({'type': 'initial_data', **data}, cls=DecimalEncoder)}\n\n"

            while True:
                await asyncio.sleep(5)
                try:
                    # Get updated data
                    new_data = await self.get_all_data(request.user, subscription)
                    yield f"data: {json.dumps({'type': 'update', **new_data}, cls=DecimalEncoder)}\n\n"
                except Exception as e:
                    print(f"Error generating event: {e}")
                    yield f"event: error\ndata: {str(e)}\n\n"
                    break
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"

    @method_decorator(csrf_exempt)
    async def get(self, request):
        # Extract token from query params
        token = request.GET.get('token')
        if not token:
            return StreamingHttpResponse(
                "event: error\ndata: No token provided\n\n",
                content_type='text/event-stream'
            )

        # Set the token in the request
        request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'

        try:
            # Authenticate the user
            user = JWTAuthentication().authenticate(request)
            if not user:
                return StreamingHttpResponse(
                    "event: error\ndata: Unauthorized\n\n",
                    content_type='text/event-stream'
                )

            response = StreamingHttpResponse(
                self.generate_events(request),
                content_type='text/event-stream'
            )

            # Add CORS headers
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Credentials"] = "true"
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'

            return response
        except Exception as e:
            return StreamingHttpResponse(
                f"event: error\ndata: {str(e)}\n\n",
                content_type='text/event-stream'
            )