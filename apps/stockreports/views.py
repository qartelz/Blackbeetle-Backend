from django.shortcuts import render, get_object_or_404
from django.http import FileResponse
from django.utils import timezone
from rest_framework import viewsets, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import action
from rest_framework.views import APIView
import os

from .models import StockReport
from .serializers import StockReportSerializer


class StockReportViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing stock reports. Only admins can perform CRUD operations.
    """
    queryset = StockReport.objects.all().order_by('-date_created')
    serializer_class = StockReportSerializer
    permission_classes = [IsAdminUser]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by strategy
        strategy_filter = self.request.query_params.get('strategy')
        if strategy_filter:
            queryset = queryset.filter(strategy=strategy_filter)

        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(date_created__range=[start_date, end_date])

        return queryset

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            partial = kwargs.pop('partial', False)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)

            # Handle status changes
            if 'status' in request.data:
                if request.data['status'] == StockReport.Status.EXPIRED:
                    instance.expired_at = timezone.now()
                else:
                    instance.expired_at = None

            self.perform_update(serializer)
            return Response(serializer.data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            if instance.pdf_upload:
                if os.path.exists(instance.pdf_upload.path):
                    os.remove(instance.pdf_upload.path)
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['GET'])
    def download_pdf(self, request, pk=None):
        report = self.get_object()
        if not report.pdf_upload:
            return Response({"error": "No PDF file available"}, status=status.HTTP_404_NOT_FOUND)

        try:
            response = FileResponse(report.pdf_upload.open('rb'), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{report.pdf_upload.name}"'
            return response
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['PATCH'])
    def publish(self, request, pk=None):
        report = self.get_object()
        if report.status != StockReport.Status.DRAFT:
            return Response({"error": "Only draft reports can be published"}, status=status.HTTP_400_BAD_REQUEST)

        report.status = StockReport.Status.PUBLISHED
        report.save()
        serializer = self.get_serializer(report)
        return Response(serializer.data)

    @action(detail=True, methods=['PATCH'])
    def expire(self, request, pk=None):
        report = self.get_object()
        if report.status == StockReport.Status.EXPIRED:
            return Response({"error": "Report is already expired"}, status=status.HTTP_400_BAD_REQUEST)

        report.status = StockReport.Status.EXPIRED
        report.expired_at = timezone.now()
        report.save()
        serializer = self.get_serializer(report)
        return Response(serializer.data)


class StockReportListView(generics.ListAPIView):
    serializer_class = StockReportSerializer
    permission_classes = [IsAdminUser]
    queryset = StockReport.objects.all().order_by('-date_created')
    
    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        strategy_filter = self.request.query_params.get('strategy')
        if strategy_filter:
            queryset = queryset.filter(strategy=strategy_filter)

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(date_created__range=[start_date, end_date])

        return queryset


class StockReportDetailView(generics.RetrieveAPIView):
    queryset = StockReport.objects.all()
    serializer_class = StockReportSerializer
    permission_classes = [IsAdminUser]


class StockReportCreateView(generics.CreateAPIView):
    queryset = StockReport.objects.all()
    serializer_class = StockReportSerializer
    permission_classes = [IsAdminUser]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StockReportUpdateView(generics.UpdateAPIView):
    queryset = StockReport.objects.all()
    serializer_class = StockReportSerializer
    permission_classes = [IsAdminUser]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            partial = kwargs.pop('partial', False)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)

            # Handle status changes
            if 'status' in request.data:
                if request.data['status'] == StockReport.Status.EXPIRED:
                    instance.expired_at = timezone.now()
                else:
                    instance.expired_at = None

            self.perform_update(serializer)
            return Response(serializer.data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StockReportDeleteView(generics.DestroyAPIView):
    queryset = StockReport.objects.all()
    serializer_class = StockReportSerializer
    permission_classes = [IsAdminUser]

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            if instance.pdf_upload:
                if os.path.exists(instance.pdf_upload.path):
                    os.remove(instance.pdf_upload.path)
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
