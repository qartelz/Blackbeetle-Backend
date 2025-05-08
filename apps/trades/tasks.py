from celery import shared_task
import pandas as pd
from datetime import datetime
from django.core.files.storage import default_storage
from .models import Company, InstrumentType

@shared_task
def process_csv_file(file_path):
    try:
        # Read the file from storage
        with default_storage.open(file_path) as file:
            df = pd.read_csv(file, low_memory=False)

        # Expected columns in the CSV
        required_columns = [
            'tokenId', 'exchange', 'tradingSymbol', 'scriptName',
            'expiryDate', 'optionType', 'segment', 'displayName'
        ]
        
        # Validate required columns
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

        def convert_date(date_str):
            if pd.isna(date_str) or date_str == '':
                return None
            try:
                # Parse the date from DD-MMM-YYYY format
                return datetime.strptime(str(date_str), '%d-%b-%Y').date()
            except Exception:
                return None

        def determine_instrument_type(segment, option_type):
            if pd.isna(segment) or segment == '':
                return InstrumentType.EQUITY
            
            segment = str(segment).upper()
            option_type = str(option_type).upper() if not pd.isna(option_type) else ''
            
            if segment == 'FUT':
                return InstrumentType.FUTURE
            elif segment == 'OPT':
                if option_type == 'CE':
                    return InstrumentType.CALL_OPTION
                elif option_type == 'PE':
                    return InstrumentType.PUT_OPTION
            return InstrumentType.EQUITY

        processed_count = 0
        errors = []
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                # Skip if token_id is not numeric
                if not str(row['tokenId']).isdigit():
                    errors.append(f"Row {idx + 1}: Invalid token_id format")
                    continue

                token_id = int(row['tokenId'])

                # Skip if token_id already exists
                if Company.objects.filter(token_id=token_id).exists():
                    errors.append(f"Row {idx + 1}: Duplicate token_id {token_id}")
                    continue

                # Skip if any required field is empty
                if any(pd.isna(row[col]) or str(row[col]).strip() == '' 
                      for col in ['tokenId', 'exchange', 'tradingSymbol', 'scriptName', 'displayName']):
                    errors.append(f"Row {idx + 1}: Missing required fields")
                    continue

                # Determine instrument type
                instrument_type = determine_instrument_type(row['segment'], row['optionType'])
                
                # Convert expiry date
                expiry_date = convert_date(row['expiryDate'])
                
                # Validate expiry date for futures and options
                if instrument_type in [InstrumentType.FUTURE, InstrumentType.CALL_OPTION, InstrumentType.PUT_OPTION]:
                    if not expiry_date:
                        errors.append(f"Row {idx + 1}: Invalid or missing expiry date for F&O instrument")
                        continue

                # Create company
                Company.objects.create(
                    token_id=token_id,
                    exchange=row['exchange'],
                    trading_symbol=row['tradingSymbol'],
                    script_name=row['scriptName'],
                    expiry_date=expiry_date,
                    display_name=row['displayName'],
                    instrument_type=instrument_type
                )
                processed_count += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 1}: {str(e)}")
        
        # Clean up the temporary file
        default_storage.delete(file_path)
        
        result = {
            "success": True,
            "processed_count": processed_count,
            "error_count": len(errors),
            "errors": errors[:100]  # Limit error messages to first 100
        }
        
        return result
        
    except Exception as e:
        # Clean up the file in case of error
        default_storage.delete(file_path)
        return {
            "success": False,
            "error": str(e),
            "processed_count": 0,
            "error_count": 0,
            "errors": []
        }