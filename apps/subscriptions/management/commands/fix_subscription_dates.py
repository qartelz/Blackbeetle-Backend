from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.subscriptions.models import Subscription
from datetime import timedelta

class Command(BaseCommand):
    help = 'Fix subscription dates to use current date and time'

    def handle(self, *args, **options):
        now = timezone.now()
        
        # Get all active subscriptions
        subscriptions = Subscription.objects.filter(is_active=True)
        
        for subscription in subscriptions:
            # Update start_date to current time
            subscription.start_date = now
            # Update end_date to be duration_days from now
            subscription.end_date = now + timedelta(days=subscription.plan.duration_days)
            subscription.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Updated subscription {subscription.id} for user {subscription.user.email}'
                    f'\nStart date: {subscription.start_date}'
                    f'\nEnd date: {subscription.end_date}'
                )
            ) 