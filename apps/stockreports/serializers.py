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
        read_only_fields = ['date_created', 'updated_at']

    def validate_pdf_upload(self, value):
        if value:
            # Validate file size (max 10MB)
            if value.size > 10 * 1024 * 1024:
                raise serializers.ValidationError("PDF file size should not exceed 10MB")
            
            # Validate file type
            if not value.name.endswith('.pdf'):
                raise serializers.ValidationError("Only PDF files are allowed")
        
        return value

    def validate(self, data):
        # Validate status transitions
        if self.instance and 'status' in data:
            if self.instance.status == StockReport.Status.EXPIRED and data['status'] != StockReport.Status.EXPIRED:
                raise serializers.ValidationError("Cannot change status of an expired report")
            
            if self.instance.status == StockReport.Status.PUBLISHED and data['status'] == StockReport.Status.DRAFT:
                raise serializers.ValidationError("Cannot change status from PUBLISHED to DRAFT")
        
        return data 