from celery import shared_task

@shared_task
def add(x, y):
    for i in range(10):
        print(i)
    return x + y