from rest_framework import serializers
from ..models import Trade, Analysis, TradeHistory, Company,Insight
from django.utils import timezone
from django.core.exceptions import ValidationError

class TradeHistorySerializer(serializers.ModelSerializer):
    risk_reward_ratio = serializers.FloatField(read_only=True)
    potential_profit_percentage = serializers.FloatField(read_only=True)
    stop_loss_percentage = serializers.FloatField(read_only=True)

    class Meta:
        model = TradeHistory
        fields = [
            'id',
            'buy', 'target', 'sl', 'timestamp',
            'risk_reward_ratio', 'potential_profit_percentage',
            'stop_loss_percentage'
        ]
        read_only_fields = ['timestamp']

class AnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = [
            'bull_scenario', 'bear_scenario', 'status',
            'completed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['completed_at', 'created_at', 'updated_at']

class CompanyMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'trading_symbol', 'exchange', 'segment', 'display_name']

class TradeListSerializer(serializers.ModelSerializer):
    company = CompanyMinimalSerializer()
    latest_history = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        fields = [
            'id', 'company', 'trade_type', 'status',
            'plan_type', 'warzone', 'is_free_call',
            'created_at', 'latest_history'
        ]

    def get_latest_history(self, obj):
        latest = obj.history.first()  # This will work because of ordering in model
        if latest:
            return TradeHistorySerializer(latest).data
        return None

class TradeCreateSerializer(serializers.ModelSerializer):
    analysis = AnalysisSerializer(required=False)
    image = serializers.ImageField(required=False)
    # warzone = serializers.IntegerField(required=False)
    warzone = serializers.DecimalField(
    max_digits=10,  # Total number of digits
    decimal_places=2,  # Number of digits after decimal point
    required=False,
    allow_null=True  # Optional, depending on your requirements
    )
    
    class Meta:
        model = Trade
        fields = [
            'company', 'trade_type', 'plan_type',
            'warzone', 'is_free_call', 'image',
            'analysis'
        ]

    def validate(self, data):
        company = data.get('company')
        trade_type = data.get('trade_type')
        
        available_types = Trade.get_available_trade_types(company.token_id)
        print(available_types,'///////////////////////////////////available_types/////////////////////////////////')
        if trade_type not in available_types:
            if len(available_types) == 0:
                raise ValidationError(f'Active or pending positional and intraday trades exist for {company.trading_symbol}. Please monitor the status and make informed trading decisions.')
            raise ValidationError(
                f"Trade type '{trade_type}' is not available for this company. "
                f"Available types: {', '.join(available_types)}"
            )
        
        return data

    def create(self, validated_data):
        # Extract nested analysis data if it exists
        analysis_data = validated_data.pop('analysis', None)

        warzone_value = validated_data.get('warzone')
        
        # Create the trade instance
        trade = Trade.objects.create(**validated_data)
        
        if warzone_value is not None:
            trade.update_warzone(warzone_value)
        # Create associated analysis if data was provided
        if analysis_data:
            Analysis.objects.create(trade=trade, **analysis_data)
        
        return trade

# class TradeUpdateSerializer(serializers.ModelSerializer):
#     image = serializers.ImageField(required=False)
#     class Meta:
#         model = Trade
#         fields = ['status', 'warzone', 'image']

#     def update(self, instance, validated_data):
#         if 'status' in validated_data:
#             new_status = validated_data['status']
#             if new_status != instance.status:
#                 if new_status in [Trade.Status.COMPLETED, Trade.Status.CANCELLED]:
#                     validated_data['completed_at'] = timezone.now()
        
#         return super().update(instance, validated_data)

class TradeUpdateSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False)
    
    class Meta:
        model = Trade
        fields = ['status', 'warzone', 'image']

    def update(self, instance, validated_data):
        # Handle status update
        if 'status' in validated_data:
            new_status = validated_data['status']
            if new_status != instance.status:
                if new_status in [Trade.Status.COMPLETED, Trade.Status.CANCELLED]:
                    validated_data['completed_at'] = timezone.now()
        
        # Handle warzone update
        if 'warzone' in validated_data:
            new_warzone = validated_data['warzone']
            
            # Use the model's update_warzone method to track history
            instance.update_warzone(new_warzone)
            
            # Remove warzone from validated_data to prevent redundant update
            validated_data.pop('warzone', None)
        
        return super().update(instance, validated_data)
    
class TradeSerializer(serializers.ModelSerializer):
    company = CompanyMinimalSerializer()
    history = TradeHistorySerializer(many=True, read_only=True)
    analysis = AnalysisSerializer(read_only=True)
    
    class Meta:
        model = Trade
        fields = [
            'id', 'company', 'user', 'trade_type',
            'status', 'plan_type', 'warzone',
            'is_free_call', 'image', 'created_at',
            'updated_at', 'completed_at', 'history',
            'analysis','warzone_history'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at', 'completed_at']
















class TradeHistoryDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeHistory
        fields = [
            'buy', 'target', 'sl', 'timestamp',
            'risk_reward_ratio', 'potential_profit_percentage',
            'stop_loss_percentage'
        ]

class AnalysisDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = [
            'bull_scenario', 'bear_scenario', 'status',
            'completed_at', 'created_at', 'updated_at'
        ]

class InsightDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insight
        fields = [
            'prediction_image', 'actual_image',
            'prediction_description', 'actual_description',
            'accuracy_score', 'analysis_result'
        ]

class TradeDetailSerializer(serializers.ModelSerializer):
    history = TradeHistoryDetailSerializer(many=True, read_only=True)
    analysis = AnalysisDetailSerializer(read_only=True)
    insight = InsightDetailSerializer(read_only=True)

    class Meta:
        model = Trade
        fields = [
            'id', 'trade_type', 'status', 'plan_type',
            'warzone', 'is_free_call', 'image',
            'created_at', 'updated_at', 'completed_at',
            'history', 'analysis', 'insight'
        ]

class CompanyTradesSerializer(serializers.ModelSerializer):
    intraday_trade = serializers.SerializerMethodField()
    positional_trade = serializers.SerializerMethodField()
    
    class Meta:
        model = Company
        fields = [
            'id', 'trading_symbol', 'exchange', 'segment',
            'display_name', 'script_name', 'expiry_date',
            'instrument_type', 'intraday_trade', 'positional_trade'
        ]
    
    def get_intraday_trade(self, obj):
        trade = obj.trades.filter(
            trade_type=Trade.TradeType.INTRADAY,status__in=['ACTIVE', 'COMPLETED']
        ).first()
        return TradeDetailSerializer(trade).data if trade else None
    
    def get_positional_trade(self, obj):
        trade = obj.trades.filter(
            trade_type=Trade.TradeType.POSITIONAL,status__in=['ACTIVE', 'COMPLETED']
        ).first()
        return TradeDetailSerializer(trade).data if trade else None