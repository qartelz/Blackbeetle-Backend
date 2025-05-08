import json
import redis
from django.conf import settings

class RedisClient:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB
        )
        self.pubsub = self.redis_client.pubsub()

    def publish_trade_update(self, channel, data):
        """Publish trade updates to Redis channel"""
        try:
            message = json.dumps(data)
            self.redis_client.publish(channel, message)
            return True
        except Exception as e:
            print(f"Error publishing to Redis: {str(e)}")
            return False