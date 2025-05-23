from rest_framework import serializers
from ..models import Trade, Analysis, IndexAndCommodity
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
User = get_user_model()

class AnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = [
            'id',
            'bull_scenario',
            'bear_scenario',
            'status',
            'completed_at',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['completed_at', 'created_at', 'updated_at']
        extra_kwargs = {
            'bull_scenario': {'required': False, 'allow_blank': True},
            'bear_scenario': {'required': False, 'allow_blank': True},
            'status': {'required': False}
        }

class TradeSerializer(serializers.ModelSerializer):
    analysis = AnalysisSerializer(source='index_and_commodity_analysis', read_only=True)
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
            'user',
            'trade_type',
            'status',
            'plan_type',
            'warzone',
            'warzone_history',
            'image',
            'created_at',
            'updated_at',
            'completed_at',
            'analysis'
        ]
        read_only_fields = [
            'created_at', 
            'updated_at', 
            'completed_at', 
            'warzone_history',
            'index_symbol',
            'user'
        ]
        extra_kwargs = {
            'index_and_commodity': {'write_only': True}
        }

    def validate(self, data):
        """
        Custom validation for trade creation and updates
        """
        # Get the index_and_commodity instance
        index_and_commodity = data.get('index_and_commodity')
        trade_type = data.get('trade_type')
        status = data.get('status', Trade.Status.PENDING)

        if not index_and_commodity:
            raise serializers.ValidationError({
                "index_and_commodity": "This field is required."
            })

        if not trade_type:
            raise serializers.ValidationError({
                "trade_type": "This field is required."
            })

        # Check for existing active trades for this index
        existing_trades = Trade.objects.filter(
            index_and_commodity=index_and_commodity,
            status__in=[Trade.Status.PENDING, Trade.Status.ACTIVE]
        )

        if self.instance:
            existing_trades = existing_trades.exclude(pk=self.instance.pk)

        if existing_trades.exists():
            existing_trade_type = existing_trades.first().trade_type
            if existing_trade_type == trade_type:
                raise serializers.ValidationError(
                    f"A {trade_type.lower()} trade already exists for this index. "
                    f"Only one {trade_type.lower()} trade is allowed per index."
                )
            elif len(existing_trades) >= 2:
                raise serializers.ValidationError(
                    "Maximum limit of trades reached for this index. "
                    "Only one intraday and one positional trade are allowed."
                )

        # Validate status transitions
        if self.instance and self.instance.status == Trade.Status.COMPLETED:
            raise serializers.ValidationError(
                "Cannot modify a completed trade."
            )

        return data

    def validate_warzone(self, value):
        """
        Validate warzone value
        """
        if value < 0:
            raise serializers.ValidationError(
                "Warzone value cannot be negative."
            )
        return value

    def validate_image(self, value):
        """
        Validate uploaded image
        """
        if value:
            if value.size > 5 * 1024 * 1024:  # 5MB limit
                raise serializers.ValidationError(
                    "Image size cannot exceed 5MB."
                )
            
            allowed_types = ['image/jpeg', 'image/png', 'image/jpg']
            if hasattr(value, 'content_type') and value.content_type not in allowed_types:
                raise serializers.ValidationError(
                    "Only JPEG and PNG images are allowed."
                )
        return value

    def create(self, validated_data):
        try:
            request = self.context.get('request')
            if not request or not request.user or not request.user.is_authenticated:
                raise serializers.ValidationError("Authentication required")

            analysis_data = validated_data.pop('index_and_commodity_analysis', None)
            
            # Set the user from the request
            validated_data['user'] = request.user
            
            trade = Trade.objects.create(**validated_data)
            
            # Create analysis with any combination of fields (or none)
            if analysis_data:
                Analysis.objects.create(trade=trade, **analysis_data)
                
            return trade
        except Exception as e:
            raise serializers.ValidationError(str(e))

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