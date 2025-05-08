from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser,AllowAny
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Avg, Count, F
from django.core.cache import cache
from rest_framework.views import APIView
from datetime import timedelta
from django.utils.timezone import now
from django.db.models import Q, Avg, Count, F
from django.core.cache import cache
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from .models import Accuracy, Trade
from .serializers import TradeSerializer,TradeSerializers
from .models import Accuracy
from .serializers import AccuracySerializer
from django.db import DatabaseError
import logging

class AccuracyCreateView(generics.CreateAPIView):
    queryset = Accuracy.objects.select_related('trade').all()
    serializer_class = AccuracySerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        """Ensures only one Accuracy record exists per trade by updating or keeping the latest one."""
        trade_id = request.data.get("trade")

        if not trade_id:
            return Response({"error": "Trade ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
               
                existing_entries = Accuracy.objects.filter(trade_id=trade_id).order_by("-created_at")

                if existing_entries.count() > 1:
                   
                    latest_entry = existing_entries.first()
                    Accuracy.objects.filter(trade_id=trade_id).exclude(id=latest_entry.id).delete()
                    accuracy_instance = latest_entry
                elif existing_entries.exists():
                    accuracy_instance = existing_entries.first()
                else:
                    accuracy_instance = None

                if accuracy_instance:
                    
                    accuracy_instance.target_hit = request.data.get("target_hit", accuracy_instance.target_hit)
                    accuracy_instance.exit_price = request.data.get("exit_price", accuracy_instance.exit_price)
                    accuracy_instance.save(update_fields=["target_hit", "exit_price"])
                    return Response(AccuracySerializer(accuracy_instance).data, status=status.HTTP_200_OK)

              
                accuracy_instance = Accuracy.objects.create(
                    trade_id=trade_id,
                    target_hit=request.data.get("target_hit", False),
                    exit_price=request.data.get("exit_price", None),
                )
                return Response(AccuracySerializer(accuracy_instance).data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": "Something went wrong", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

# class AccuracyCreateView(generics.CreateAPIView):
#     queryset = Accuracy.objects.select_related('trade').all()
#     serializer_class = AccuracySerializer
#     permission_classes = [AllowAny]

#     def create(self, request, *args, **kwargs):
#         """Ensure only one Accuracy record exists per trade by updating or replacing duplicates."""
#         trade_id = request.data.get("trade")

#         if not trade_id:
#             return Response({"error": "Trade ID is required"}, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             with transaction.atomic():
#                 # Delete existing duplicate records (if any)
#                 Accuracy.objects.filter(trade_id=trade_id).delete()

#                 # Create a fresh new Accuracy record
#                 accuracy_instance = Accuracy.objects.create(
#                     trade_id=trade_id,
#                     target_hit=request.data.get("target_hit", False),
#                     exit_price=request.data.get("exit_price", None),
#                     # total_days=request.data.get("total_days", 0),
#                 )

#                 return Response(AccuracySerializer(accuracy_instance).data, status=status.HTTP_201_CREATED)

#         except ValidationError as e:
#             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
#         except Exception as e:
#             return Response({"error": "Something went wrong", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# class AccuracyCreateView(generics.CreateAPIView):
#     queryset = Accuracy.objects.select_related('trade').all()  # Optimized query
#     serializer_class = AccuracySerializer
#     permission_classes = [IsAdminUser]  # Ensure authenticated access

#     def create(self, request, *args, **kwargs):
#         """Optimized create method with DB transaction for performance."""
#         try:
#             with transaction.atomic():  # Ensures data integrity
#                 return super().create(request, *args, **kwargs)
#         except ValidationError as e:
#             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

class AccuracyListCreateView(generics.ListCreateAPIView):
    """View to list and create Accuracy records"""
    queryset = Accuracy.objects.select_related('trade').all()  # Optimized query
    serializer_class = AccuracySerializer
    permission_classes = [AllowAny]  

    def create(self, request, *args, **kwargs):
        """Optimized create method with DB transaction for performance."""
        try:
            with transaction.atomic():  # Ensures data integrity
                return super().create(request, *args, **kwargs)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AccuracyByTradeView(generics.ListAPIView):
    """Returns Accuracy entries for a specific Trade ID."""
    serializer_class = AccuracySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        trade_id = self.kwargs.get('trade_id')
        return Accuracy.objects.filter(trade_id=trade_id).select_related('trade')
    

# API 1: Trade Statistics (Avg Duration, Total Trades, Success Rate)
class TradeStatisticsView(APIView):
    """API to get trade statistics: average duration, total completed trades, success rate"""
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        cache_key = "trade_statistics"
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data, status=200)

        # Filter only COMPLETED trades
        completed_trades = Trade.objects.filter(status="COMPLETED")

        # Get IDs of completed trades
        completed_trade_ids = completed_trades.values_list("id", flat=True)

        # Accuracy stats only for completed trades
        accuracy_stats = Accuracy.objects.filter(trade_id__in=completed_trade_ids).aggregate(
            avg_days=Avg("total_days"),
            successful_trades=Count("id", filter=Q(target_hit=True))
        )

        completed_trades_count = completed_trades.count()
        successful_trades = accuracy_stats.get("successful_trades", 0)

        # Calculate success rate based only on completed trades
        success_rate = (successful_trades / completed_trades_count * 100) if completed_trades_count > 0 else 0

        response_data = {
            "average_trade_duration": round(accuracy_stats["avg_days"], 2) if accuracy_stats["avg_days"] else 0,
            "total_trades": completed_trades_count,
            "success_rate": round(success_rate, 2)
        }

        # Cache result for 5 minutes
        cache.set(cache_key, response_data, timeout=300)

        return Response(response_data, status=200)

# class TradeStatisticsView(APIView):
#     """API to get trade statistics: average duration, total trades, success rate"""
#     permission_classes = [AllowAny]

#     def get(self, request, *args, **kwargs):
#         cache_key = "trade_statistics"
#         cached_data = cache.get(cache_key)

#         if cached_data:
#             return Response(cached_data, status=200)

#         # Aggregate statistics from Accuracy model
#         stats = Accuracy.objects.aggregate(
#             avg_days=Avg("total_days"),
#             successful_trades=Count("id", filter=F("target_hit"))
#         )

#         # Count completed trades
#         completed_trades_count = Trade.objects.filter(status="COMPLETED").count()

#         # Count last 30 days active trades
#         last_30_days = now() - timedelta(days=30)
#         active_trades_last_30_days = Trade.objects.filter(status="ACTIVE" , created_at__gte=last_30_days)\
#                                             .order_by("-created_at")[:6]\
#                                             .count()

#         # Total trades = all completed trades + last 30 days active trades
#         total_trades = completed_trades_count + active_trades_last_30_days
#         successful_trades = stats.get("successful_trades", 0)

#         # Calculate success rate
#         success_rate = (successful_trades / total_trades * 100) if total_trades > 0 else 0

#         response_data = {
#             "average_trade_duration": round(stats["avg_days"], 2) if stats["avg_days"] else 0,
#             "total_trades": total_trades,
#             "success_rate": round(success_rate, 2)  # In percentage
#         }

#         # Cache result for 5 minutes
#         cache.set(cache_key, response_data, timeout=300)

#         return Response(response_data, status=200)

# class TradeStatisticsView(APIView):
#     """API to get trade statistics: average duration, total trades, success rate"""
#     permission_classes = [AllowAny]

#     def get(self, request, *args, **kwargs):
#         cache_key = "trade_statistics"
#         cached_data = cache.get(cache_key)

#         if cached_data:
#             return Response(cached_data, status=200)

#         # Aggregate statistics
#         stats = Accuracy.objects.aggregate(
#             avg_days=Avg("total_days"),
#             total_trades=Count("id"),
#             successful_trades=Count("id", filter=F("target_hit"))
#         )

#         total_trades = stats.get("total_trades", 0)
#         successful_trades = stats.get("successful_trades", 0)

#         # Calculate success rate
#         success_rate = (successful_trades / total_trades * 100) if total_trades > 0 else 0

#         response_data = {
#             "average_trade_duration": round(stats["avg_days"], 2) if stats["avg_days"] else 0,
#             "total_trades": total_trades,
#             "success_rate": round(success_rate, 2)  # In percentage
#         }

#         # Cache result for 5 minutes
#         cache.set(cache_key, response_data, timeout=300)

#         return Response(response_data, status=200)



# API 2: Active Trades in Last 30 Days


class ActiveTradesView(APIView):
    """API to get active trades in the last 30 days (max 6 trades)"""
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        cache_key = "active_trades"

        try:
            # Try to fetch from cache
            cached_data = cache.get(cache_key)
            if cached_data:
                return Response(cached_data, status=status.HTTP_200_OK)
        except Exception as e:
            # Log cache errors (optional: replace with logging)
            print(f"Cache error: {e}")

        try:
            last_30_days = now() - timedelta(days=30)

            # Fetch only the latest 6 active trades
            active_trades = Trade.objects.filter(
                status="ACTIVE", plan_type="BASIC", created_at__gte=last_30_days
            ).order_by("-created_at")[:6]

            active_trades_data = TradeSerializer(active_trades, many=True).data

            response_data = {
                "active_trades_last_30_days": len(active_trades_data),  # Count only the returned trades
                "active_trades": active_trades_data
            }

            try:
                # Cache result for 5 minutes
                cache.set(cache_key, response_data, timeout=300)
            except Exception as e:
                print(f"Cache set error: {e}")

            return Response(response_data, status=status.HTTP_200_OK)

        except ValidationError as e:
            return Response({"error": "Invalid request data", "details": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except DatabaseError as e:
            return Response({"error": "Database error", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            return Response({"error": "An unexpected error occurred", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# API 3: All-time Completed Trades
logger = logging.getLogger(__name__)
class CompletedTradesView(APIView):
    """API to get all-time completed trades with additional details"""
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        cache_key = "completed_trades_v1"  # Versioning to avoid stale cache
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data, status=200)

        try:
            # Optimized Query - Fetch only necessary fields
            completed_trades = (
                Trade.objects.filter(status="COMPLETED")
                .select_related("analysis")  # Use select_related for single FK
                .prefetch_related("history")  # Prefetch for ManyToMany or Reverse FK
            )
            
            completed_trades_data = TradeSerializers(completed_trades, many=True).data

            response_data = {
                "total_completed_trades": completed_trades.count(),
                "completed_trades": completed_trades_data,
            }

            # Cache result for 5 minutes
            cache.set(cache_key, response_data, timeout=300)
            return Response(response_data, status=200)
        
        except Exception as e:
            logger.error(f"Error fetching completed trades: {str(e)}", exc_info=True)
            return Response({"error": "Internal Server Error"}, status=500)
