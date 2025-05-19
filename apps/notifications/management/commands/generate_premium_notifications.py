from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from apps.trades.models import Trade
from apps.subscriptions.models import Subscription
from apps.notifications.models import Notification
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Generates notifications for SUPER_PREMIUM and FREE_TRIAL users for all existing trades'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=str, help='Specific user ID to generate notifications for')
        parser.add_argument('--dry-run', action='store_true', help='Run without actually creating notifications')

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        dry_run = options.get('dry_run', False)
        
        self.stdout.write(f"{'DRY RUN: ' if dry_run else ''}Generating notifications for premium users...")
        
        # Get active SUPER_PREMIUM and FREE_TRIAL subscriptions
        subscription_query = Subscription.objects.filter(
            is_active=True,
            start_date__lte=timezone.now(),
            end_date__gt=timezone.now(),
            plan__name__in=['SUPER_PREMIUM', 'FREE_TRIAL']
        ).select_related('user')
        
        # Filter by user_id if provided
        if user_id:
            subscription_query = subscription_query.filter(user_id=user_id)
            
        # Get all users with premium subscriptions
        premium_users = list(subscription_query)
        self.stdout.write(f"Found {len(premium_users)} premium users")
        
        if not premium_users:
            self.stdout.write(self.style.WARNING("No eligible premium users found"))
            return
        
        # Get all active and completed trades
        trades = Trade.objects.filter(
            status__in=['ACTIVE', 'COMPLETED']
        ).select_related('company')
        
        self.stdout.write(f"Found {trades.count()} trades to process")
        
        # Get trade content type for notification creation
        trade_content_type = ContentType.objects.get_for_model(Trade)
        
        # Track statistics
        total_created = 0
        users_processed = 0
        
        # Process each premium user
        for subscription in premium_users:
            user = subscription.user
            self.stdout.write(f"Processing user: {user.id}")
            
            try:
                with transaction.atomic():
                    if dry_run:
                        # In dry run mode, just count what would be created
                        # Get existing notification trade IDs for this user
                        existing_notification_trade_ids = set(Notification.objects.filter(
                            recipient=user,
                            content_type=trade_content_type
                        ).values_list('trade_id', flat=True))
                        
                        # Count missing notifications
                        missing_count = sum(1 for trade in trades if trade.id not in existing_notification_trade_ids)
                        self.stdout.write(f"  User {user.id} would receive {missing_count} new notifications")
                        total_created += missing_count
                    else:
                        # Get existing notification trade IDs for this user
                        existing_notification_trade_ids = set(Notification.objects.filter(
                            recipient=user,
                            content_type=trade_content_type
                        ).values_list('trade_id', flat=True))
                        
                        # Create notifications for missing trades
                        created_count = 0
                        for trade in trades:
                            if trade.id not in existing_notification_trade_ids:
                                # Create a notification for this trade
                                if trade.status == 'COMPLETED':
                                    notification_type = 'TRADE'
                                    short_message = f"Trade completed: {trade.company.trading_symbol}"
                                    detailed_message = f"The trade for {trade.company.trading_symbol} has been completed"
                                else:
                                    notification_type = 'TRADE'
                                    short_message = f"Trade updated: {trade.company.trading_symbol}"
                                    detailed_message = f"The trade for {trade.company.trading_symbol} has been updated"
                                    
                                # Create the notification
                                Notification.objects.create(
                                    recipient=user,
                                    notification_type=notification_type,
                                    content_type=trade_content_type,
                                    object_id=trade.id,
                                    short_message=short_message,
                                    detailed_message=detailed_message,
                                    trade_status=trade.status,
                                    is_redirectable=True,
                                    trade_id=trade.id,
                                    related_url=f"/trades/{trade.id}"
                                )
                                created_count += 1
                        
                        self.stdout.write(f"  Created {created_count} notifications for user {user.id}")
                        total_created += created_count
                
                users_processed += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing user {user.id}: {str(e)}"))
                logger.error(f"Error generating notifications for user {user.id}: {str(e)}")
                continue
            
        # Summary
        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"DRY RUN COMPLETE: Would create {total_created} notifications for {users_processed} premium users"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Successfully created {total_created} notifications for {users_processed} premium users"
            )) 