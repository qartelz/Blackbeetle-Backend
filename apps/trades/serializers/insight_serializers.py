from rest_framework import serializers
from ..models import Insight

class InsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insight
        fields = [
            'id', 'trade', 'prediction_image', 'actual_image',
            'prediction_description', 'actual_description',
            'accuracy_score', 'analysis_result', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'trade', 'created_at', 'updated_at']

class InsightCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insight
        fields = [
            'prediction_image', 'actual_image', 'prediction_description',
            'actual_description', 'accuracy_score', 'analysis_result'
        ]

    def validate(self, data):
        if self.instance:
            # For updates, all fields are optional
            return data
        
        # For creation, ensure all required fields are present
        required_fields = ['prediction_image', 'prediction_description']
        for field in required_fields:
            if field not in data:
                raise serializers.ValidationError(f"{field} is required for creating an insight.")
        return data
