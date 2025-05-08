from django.contrib import admin
from .models import Trade,TradeHistory,Company
# Register your models here.
# admin.site.register(Segment)
admin.site.register(Trade)
admin.site.register(TradeHistory)
# admin.site.register(TradeType)
admin.site.register(Company)