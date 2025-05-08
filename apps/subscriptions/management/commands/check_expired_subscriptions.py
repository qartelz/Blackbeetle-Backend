from django.core.management.base import BaseCommand
from django.utils import timezone
from ...models import Subscription

class Command(BaseCommand):
    help = 'Check and update expired subscriptions'

    def handle(self, *args, **options):
        today = timezone.now().date()
        expired_subscriptions = Subscription.objects.filter(
            end_date__lt=today,
            is_active=True
        )

        for subscription in expired_subscriptions:
            subscription.is_active = False
            subscription.save()
            self.stdout.write(self.style.SUCCESS(f'Deactivated subscription for user {subscription.user.phone_number}'))

        self.stdout.write(self.style.SUCCESS(f'Successfully checked and updated {expired_subscriptions.count()} expired subscriptions'))