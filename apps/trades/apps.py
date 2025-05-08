from django.apps import AppConfig


# class TradesConfig(AppConfig):
#     default_auto_field = 'django.db.models.BigAutoField'
#     name = 'apps.trades'

#     def ready(self):
#         from . import signals   


from django.apps import AppConfig

class TradesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.trades'

    def ready(self):
        import apps.trades.signals  