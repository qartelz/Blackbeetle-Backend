from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.subscriptions.models import Subscription
from datetime import timedelta, datetime

class Command(BaseCommand):
    help = 'Fix subscription dates to use current date and time'

    def handle(self, *args, **options):
        # Force current year
        now = timezone.now()
        current_year = datetime.now().year
        
        # Get all active subscriptions
        subscriptions = Subscription.objects.filter(is_active=True)
        
        for subscription in subscriptions:
            # Update start_date to current time with correct year
            subscription.start_date = now.replace(year=current_year)
            # Update end_date to be duration_days from now with correct year
            subscription.end_date = (now + timedelta(days=subscription.plan.duration_days)).replace(year=current_year)
            subscription.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Updated subscription {subscription.id} for user {subscription.user.email}'
                    f'\nStart date: {subscription.start_date}'
                    f'\nEnd date: {subscription.end_date}'
                )
            ) 