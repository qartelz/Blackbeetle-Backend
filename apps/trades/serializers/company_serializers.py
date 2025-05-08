from rest_framework import serializers
from ..models import Company

class CompanySerializer(serializers.ModelSerializer):
    segment = serializers.CharField(required=False, write_only=True)
    option_type = serializers.CharField(required=False, write_only=True)
    
    class Meta:
        model = Company
        fields = [
            'id', 'token_id', 'exchange', 'trading_symbol', 
            'script_name', 'expiry_date', 'display_name',
            'segment', 'option_type', 'instrument_type'
        ]
        read_only_fields = ['instrument_type']

    def validate(self, data):
        # Handle instrument_type based on segment and option_type
        segment = data.pop('segment', None)
        option_type = data.pop('option_type', None)

        if not segment:
            data['instrument_type'] = Company.instrument_type.EQUITY
        elif segment.upper() == 'FUT':
            data['instrument_type'] = Company.instrument_type.FUTURE
            if not data.get('expiry_date'):
                raise serializers.ValidationError(
                    {"expiry_date": "Expiry date is required for futures"}
                )
        elif segment.upper() == 'OPT':
            if not option_type:
                raise serializers.ValidationError(
                    {"option_type": "Option type (CE/PE) is required for options"}
                )
            if not data.get('expiry_date'):
                raise serializers.ValidationError(
                    {"expiry_date": "Expiry date is required for options"}
                )
            
            if option_type.upper() == 'CE':
                data['instrument_type'] =Company.instrument_type.CALL_OPTION
            elif option_type.upper() == 'PE':
                data['instrument_type'] = Company.instrument_type.PUT_OPTION
            else:
                raise serializers.ValidationError(
                    {"option_type": "Option type must be either CE or PE"}
                )

        return data