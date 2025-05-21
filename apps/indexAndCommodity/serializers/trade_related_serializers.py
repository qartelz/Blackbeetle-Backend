from rest_framework import serializers
from ..models import Trade, Analysis, IndexAndCommodity
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError as DRFValidationError

User = get_user_model()

class AnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = [
            'id',
            'bull_scenario',
            'bear_scenario',
            'status',
            'created_at',
            'updated_at',
            'completed_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'completed_at']
        extra_kwargs = {
            'bull_scenario': {'required': False, 'allow_blank': True},
            'bear_scenario': {'required': False, 'allow_blank': True},
            'status': {'required': False}
        }

class TradeSerializer(serializers.ModelSerializer):
    analysis = AnalysisSerializer(
        source='index_and_commodity_analysis', 
        required=False
    )
    # available_trade_types = serializers.SerializerMethodField()
    index_symbol = serializers.CharField(
        source='index_and_commodity.tradingSymbol', 
        read_only=True
    )

    class Meta:
        model = Trade
        fields = [
            'id',
            'index_symbol',
            'index_and_commodity',
            'trade_type',
            'status',
            'plan_type',
            'warzone',
            'warzone_history',
            'image',
            'created_at',
            'updated_at',
            'completed_at',
            'analysis',
            # 'available_trade_types'
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'completed_at',
            'warzone_history',
            # 'available_trade_types',
            'index_symbol'
        ]
        extra_kwargs = {
            'index_and_commodity': {'write_only': True}
        }

    # def get_available_trade_types(self, obj):
    #     return obj.get_available_trade_types()

    def create(self, validated_data):
        try:
            # Get the user from the request context
            user = self.context['request'].user
            if not user or not user.is_authenticated:
                raise DRFValidationError("Authentication required to create a trade.")

            analysis_data = validated_data.pop('index_and_commodity_analysis', None)
            
            # Create trade with authenticated user
            trade = Trade.objects.create(user=user, **validated_data)
            
            # Create analysis if provided
            if analysis_data:
                Analysis.objects.create(trade=trade, **analysis_data)
                
            return trade
        except Exception as e:
            raise DRFValidationError(f"Failed to create trade: {str(e)}")

    def update(self, instance, validated_data):
        analysis_data = validated_data.pop('index_and_commodity_analysis', None)
        
        # Update trade fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Handle partial analysis updates
        if analysis_data is not None:
            analysis = instance.index_and_commodity_analysis
            if analysis:
                # Update only provided fields
                for key, value in analysis_data.items():
                    if value is not None:
                        setattr(analysis, key, value)
                analysis.save()
            else:
                # Create new analysis if none exists
                Analysis.objects.create(trade=instance, **analysis_data)
                
        return instance

    def validate(self, data):
        # Existing trade type validation remains
        index = data.get('index_and_commodity') or getattr(self.instance, 'index_and_commodity', None)
        trade_type = data.get('trade_type') or getattr(self.instance, 'trade_type', None)
        
        if index and trade_type:
            conflicting = Trade.objects.filter(
                index_and_commodity=index,
                trade_type=trade_type,
                status__in=[Trade.Status.PENDING, Trade.Status.ACTIVE]
            ).exclude(pk=getattr(self.instance, 'pk', None)).exists()
            
            if conflicting:
                raise ValidationError(
                     f'Cannot place {trade_type.lower()} trade: Active position exists for {index.tradingSymbol}. Please close your existing position first.'
                )
        
        return data