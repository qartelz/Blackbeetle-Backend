import os
from celery import Celery
from celery.schedules import crontab
# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('blackbeetle')


# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


app.conf.beat_schedule = {
    'check-expired-subscriptions': {
        'task': 'apps.subscriptions.tasks.check_expired_subscriptions',
        'schedule': crontab(hour=0, minute=0),
    },
}

# app.conf.beat_schedule = {
#     'check-expired-subscriptions': {
#         'task': 'apps.subscriptions.tasks.check_expired_subscriptions',
#         'schedule': crontab(minute='*/1'),  # Run every 5 minutes
#     },
# }
@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

app.conf.update(
    BROKER_URL='redis://localhost:6379/0',
    CELERY_RESULT_BACKEND='django-db',
    ACCEPT_CONTENT=['application/json'],
    TASK_SERIALIZER='json',
    RESULT_SERIALIZER='json',
    TIMEZONE='Asia/Kolkata',
    CELERY_ACKS_LATE=True,
    CELERYD_PREFETCH_MULTIPLIER=1,
    CELERY_TASK_TIME_LIMIT=30 * 60,  # 30 minutes
    CELERY_TASK_SOFT_TIME_LIMIT=15 * 60,  # 15 minutes
)