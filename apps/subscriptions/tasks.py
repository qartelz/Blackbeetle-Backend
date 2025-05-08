from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.db.models import F
from .models import Subscription

@shared_task
def check_expired_subscriptions():
    today = timezone.now().date()
    
    # Use select_for_update to prevent race conditions
    with transaction.atomic():
        """
        Use of `select_for_update(): This prevents race conditions by locking the selected rows until the transaction is complete.
        """
        expired_subscriptions = Subscription.objects.select_for_update().filter(
            end_date__lt=today,
            is_active=True
        )
        
        # Use bulk update for better performance
        deactivated_count = expired_subscriptions.update(is_active=False)
    
    return f'Successfully checked and updated {deactivated_count} expired subscriptions'

