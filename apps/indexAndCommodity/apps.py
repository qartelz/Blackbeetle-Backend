from django.apps import AppConfig


class IndexandcommodityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.indexAndCommodity'

    def ready(self):
        from . import signals
