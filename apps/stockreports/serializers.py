from rest_framework import serializers
from .models import StockReport


class StockReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockReport
        fields = [
            'id',
            'title',
            'date_created',
            'expired_at',
            'updated_at',
            'status',
            'strategy',
            'pdf_upload'
        ]
        read_only_fields = ['date_created', 'updated_at', 'expired_at']

    def validate_status(self, value):
        """
        Validate status transitions
        """
        if self.instance:  # If updating an existing instance
            if self.instance.status == StockReport.Status.EXPIRED and value != StockReport.Status.EXPIRED:
                raise serializers.ValidationError("Cannot change status of an expired report")
            
            if self.instance.status == StockReport.Status.PUBLISHED and value == StockReport.Status.DRAFT:
                raise serializers.ValidationError("Cannot change published report back to draft")
        
        return value

    def validate_pdf_upload(self, value):
        """
        Validate PDF file upload
        """
        if value:
            # Check file size (max 10MB)
            if value.size > 10 * 1024 * 1024:
                raise serializers.ValidationError("PDF file size cannot exceed 10MB")
            
            # Check file type
            if not value.name.lower().endswith('.pdf'):
                raise serializers.ValidationError("Only PDF files are allowed")
        
        return value 