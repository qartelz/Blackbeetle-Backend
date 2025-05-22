from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.http import FileResponse
import os
from rest_framework.views import APIView

from .models import StockReport
from .serializers import StockReportSerializer

class StockReportViewSet(viewsets.ModelViewSet):
    queryset = StockReport.objects.all().order_by('-date_created')
    serializer_class = StockReportSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by status
        status = self.request.query_params.get('status', None)
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by strategy
        strategy = self.request.query_params.get('strategy', None)
        if strategy:
            queryset = queryset.filter(strategy=strategy)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        if start_date and end_date:
            queryset = queryset.filter(date_created__range=[start_date, end_date])
        
        return queryset

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            # Delete the PDF file if it exists
            if instance.pdf_upload:
                if os.path.exists(instance.pdf_upload.path):
                    os.remove(instance.pdf_upload.path)
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['GET'])
    def download_pdf(self, request, pk=None):
        """Download the PDF file"""
        report = self.get_object()
        if not report.pdf_upload:
            return Response(
                {"error": "No PDF file available"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            response = FileResponse(
                report.pdf_upload.open('rb'),
                content_type='application/pdf'
            )
            response['Content-Disposition'] = f'attachment; filename="{report.pdf_upload.name}"'
            return response
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['PATCH'])
    def publish(self, request, pk=None):
        """Publish a draft report"""
        report = self.get_object()
        if report.status != StockReport.Status.DRAFT:
            return Response(
                {"error": "Only draft reports can be published"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        report.status = StockReport.Status.PUBLISHED
        report.save()
        serializer = self.get_serializer(report)
        return Response(serializer.data)

    @action(detail=True, methods=['PATCH'])
    def expire(self, request, pk=None):
        """Mark a report as expired"""
        report = self.get_object()
        if report.status == StockReport.Status.EXPIRED:
            return Response(
                {"error": "Report is already expired"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        report.status = StockReport.Status.EXPIRED
        report.expired_at = timezone.now()
        report.save()
        serializer = self.get_serializer(report)
        return Response(serializer.data)

class CreateStockReportView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        """Create a new stock report"""
        try:
            # Check if pdf_upload is in request.FILES
            if 'pdf_upload' in request.FILES:
                pdf_file = request.FILES['pdf_upload']
                # Validate content type
                if not pdf_file.content_type == 'application/pdf':
                    return Response(
                        {"error": "Invalid file type. Only PDF files are allowed."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                # Add the file to request.data
                request.data['pdf_upload'] = pdf_file

            serializer = StockReportSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(
                    {
                        "message": "Stock report created successfully",
                        "data": serializer.data
                    }, 
                    status=status.HTTP_201_CREATED
                )
            return Response(
                {
                    "error": "Validation error",
                    "details": serializer.errors
                }, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

class ListStockReportsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all stock reports with optional filters"""
        try:
            queryset = StockReport.objects.all().order_by('-date_created')
            
            # Filter by status
            status_param = request.query_params.get('status', None)
            if status_param:
                queryset = queryset.filter(status=status_param)
            
            # Filter by strategy
            strategy = request.query_params.get('strategy', None)
            if strategy:
                queryset = queryset.filter(strategy=strategy)
            
            # Filter by date range
            start_date = request.query_params.get('start_date', None)
            end_date = request.query_params.get('end_date', None)
            if start_date and end_date:
                queryset = queryset.filter(date_created__range=[start_date, end_date])
            
            serializer = StockReportSerializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

class StockReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        """Retrieve a specific stock report"""
        try:
            report = get_object_or_404(StockReport, pk=pk)
            serializer = StockReportSerializer(report)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND
            )

class UpdateStockReportView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def patch(self, request, pk):
        """Update a specific stock report"""
        try:
            report = get_object_or_404(StockReport, pk=pk)
            
            # Handle PDF file update
            if 'pdf_upload' in request.FILES:
                pdf_file = request.FILES['pdf_upload']
                # Validate content type
                if not pdf_file.content_type == 'application/pdf':
                    return Response(
                        {"error": "Invalid file type. Only PDF files are allowed."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                # Delete old PDF if it exists
                if report.pdf_upload:
                    if os.path.exists(report.pdf_upload.path):
                        os.remove(report.pdf_upload.path)
                # Add the new file to request.data
                request.data['pdf_upload'] = pdf_file

            serializer = StockReportSerializer(report, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(
                    {
                        "message": "Stock report updated successfully",
                        "data": serializer.data
                    }
                )
            return Response(
                {
                    "error": "Validation error",
                    "details": serializer.errors
                }, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

class DeleteStockReportView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        """Delete a specific stock report"""
        try:
            report = get_object_or_404(StockReport, pk=pk)
            
            # Delete the PDF file if it exists
            if report.pdf_upload:
                if os.path.exists(report.pdf_upload.path):
                    os.remove(report.pdf_upload.path)
            
            report.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

class DownloadPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        """Download the PDF file of a specific report"""
        try:
            report = get_object_or_404(StockReport, pk=pk)
            if not report.pdf_upload:
                return Response(
                    {"error": "No PDF file available"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            response = FileResponse(
                report.pdf_upload.open('rb'),
                content_type='application/pdf'
            )
            response['Content-Disposition'] = f'attachment; filename="{report.pdf_upload.name}"'
            return response
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

class PublishReportView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        """Publish a draft report"""
        try:
            report = get_object_or_404(StockReport, pk=pk)
            if report.status != StockReport.Status.DRAFT:
                return Response(
                    {"error": "Only draft reports can be published"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            report.status = StockReport.Status.PUBLISHED
            report.save()
            serializer = StockReportSerializer(report)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

class ExpireReportView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        """Mark a report as expired"""
        try:
            report = get_object_or_404(StockReport, pk=pk)
            if report.status == StockReport.Status.EXPIRED:
                return Response(
                    {"error": "Report is already expired"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            report.status = StockReport.Status.EXPIRED
            report.expired_at = timezone.now()
            report.save()
            serializer = StockReportSerializer(report)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
