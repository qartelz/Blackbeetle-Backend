from rest_framework import serializers
from ..models import FreeCallTrade, FreeCallTradeHistory, Company
from django.db import transaction
from django.db.utils import IntegrityError

class CompanyMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'trading_symbol', 'exchange', 'segment', 'display_name']

class FreeCallTradeHistorySerializer(serializers.ModelSerializer):
    risk_reward_ratio = serializers.FloatField(read_only=True)
    potential_profit_percentage = serializers.FloatField(read_only=True)
    stop_loss_percentage = serializers.FloatField(read_only=True)
    class Meta:
        model = FreeCallTradeHistory
        fields = ['buy', 'target', 'sl', 'timestamp', 'risk_reward_ratio', 'potential_profit_percentage', 'stop_loss_percentage']

class FreeCallTradeSerializer(serializers.ModelSerializer):
    company = CompanyMinimalSerializer(read_only=True)
    company_id = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.filter(trading_symbol__startswith='NIFTY'),
        write_only=True,
        source='company'
    )
    
    latest_history = serializers.SerializerMethodField()

    class Meta:
        model = FreeCallTrade
        fields = ['id', 'company', 'company_id', 'trade_type', 'status', 'sentiment', 'created_at', 'latest_history']
        read_only_fields = ['created_at']

    def get_latest_history(self, obj):
        latest = obj.history.latest()
        return FreeCallTradeHistorySerializer(latest).data if latest else None

class FreeCallTradeCreateSerializer(serializers.ModelSerializer):
    history = FreeCallTradeHistorySerializer(write_only=True)
    company = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(),
        write_only=True
    )

    class Meta:
        model = FreeCallTrade
        fields = ['company', 'trade_type', 'sentiment', 'history']

    def validate_company(self, value):
        """
        Validate that only NIFTY stocks are allowed
        """
        # if not value.trading_symbol.startswith('NIFTY'):
        #     raise serializers.ValidationError(
        #         "Only NIFTY stocks can be given as free calls."
        #     )
        return value

    def validate(self, data):
        """
        Additional validation to check for duplicate active trades
        Note: We're removing this validation since we'll handle existing trades
        in the create method by cancelling them instead of raising an error.
        """
        return data

    def create(self, validated_data):
        try:
            with transaction.atomic():
                history_data = validated_data.pop('history')
                company = validated_data.get('company')
                trade_type = validated_data.get('trade_type')
                
                # Check for existing active trade
                existing_active_trade = FreeCallTrade.objects.filter(
                    company=company,
                    trade_type=trade_type,
                    status='ACTIVE',
                    is_deleted=False
                ).first()
                
                # If an existing active trade is found, cancel and soft-delete it
                if existing_active_trade:
                    existing_active_trade.status = 'CANCELLED'
                    existing_active_trade.is_deleted = True
                    existing_active_trade.save()
                
                # Create the new trade
                free_call_trade = FreeCallTrade.objects.create(**validated_data)
                FreeCallTradeHistory.objects.create(trade=free_call_trade, **history_data)
                return free_call_trade
        except IntegrityError:
            raise serializers.ValidationError({
                "error": "Unable to create trade. A database integrity error occurred."
            })

class FreeCallTradeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FreeCallTrade
        fields = ['status', 'sentiment']