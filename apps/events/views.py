from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Event
from .serializers import EventSerializer,EventSerializers
from datetime import date
from rest_framework.permissions import IsAuthenticated
from apps.subscriptions.models import Subscription
from rest_framework.pagination import PageNumberPagination
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend


class EventAPIView(APIView):
    """
    API View to handle event creation and editing.
    """

    def post(self, request):
        """Create a new event."""
        print(request.data)
        serializer = EventSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()  # Save event to DB
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    



    def patch(self, request, pk):
        """Edit an existing event."""
        event = get_object_or_404(Event, pk=pk)  
        serializer = EventSerializer(event, data=request.data, partial=True)  #
        if serializer.is_valid():
            serializer.save()  # Save changes
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class EventUserView(APIView):
    
    permission_classes = [IsAuthenticated]  
    def get(self, request):
        """Retrieve events for authenticated users with an active Premium or Super Premium subscription."""
        allowed_plans = ["PREMIUM", "SUPER_PREMIUM"]

        # Check if the user has an active subscription
        has_valid_subscription = Subscription.objects.filter(
            user=request.user,
            plan__name__in=allowed_plans,  # Ensure the plan is Premium or Super Premium
            is_active=True,
            start_date__lte=date.today(),
            end_date__gte=date.today()
        ).exists()

        if not has_valid_subscription:
            return Response(
                {"error": "Access restricted to users with an active Premium or Super Premium subscription."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Fetch events only if the user has an active subscription
        events = Event.objects.all()
        serializer = EventSerializer(events, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

# class CustomPagination(PageNumberPagination):
#     page_size = 10
#     page_size_query_param = 'page_size'
#     max_page_size = 100

# class EventListView(APIView):
#     """
#     Returns a list of all events sorted by date and meeting start time.
#     Supports pagination and provides clear success/error responses.
#     """

#     def get(self, request):
#         try:
#             events = Event.objects.all().order_by('date', 'meeting_start_time')
            
#             # Optional: filter or optimize using select_related / prefetch_related if needed

#             paginator = CustomPagination()
#             result_page = paginator.paginate_queryset(events, request)
#             serializer = EventSerializers(result_page, many=True)

#             return paginator.get_paginated_response({
#                 "status": True,
#                 "message": "Events fetched successfully.",
#                 "data": serializer.data
#             })
#         except Exception as e:
#             return Response({
#                 "status": False,
#                 "message": "Failed to fetch events.",
#                 "error": str(e)
#             }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class EventPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class EventListView(ListAPIView):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    pagination_class = EventPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['date', 'status']
    ordering_fields = ['date', 'meeting_start_time']
    ordering = ['date', 'meeting_start_time']

    def list(self, request, *args, **kwargs):
        try:
            response = super().list(request, *args, **kwargs)
            return Response({
                "status": True,
                "message": "Events fetched successfully.",
                "data": response.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "status": False,
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)