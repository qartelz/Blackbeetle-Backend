import json
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging

logger = logging.getLogger(__name__)

def send_trade_update(trade):
    channel_layer = get_channel_layer()
    trade_data = {
        "id": trade.id,
        "company": trade.company.name,
        "segment": trade.segment.name,
        "trade_type": trade.trade_type.name,
        "user": trade.user.username,
        "expiry_date": trade.expiry_date.isoformat() if trade.expiry_date else None,
        "status": trade.status,
        "created_at": trade.created_at.isoformat(),
    }
    
    try:
        async_to_sync(channel_layer.group_send)(
            "trades",
            {
                "type": "trade_update",
                "trade": trade_data
            }
        )
        logger.info(f"Trade update sent for trade ID: {trade.id}")
    except Exception as e:
        logger.error(f"Error sending trade update: {str(e)}")

