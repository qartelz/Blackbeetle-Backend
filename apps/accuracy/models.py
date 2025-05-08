from django.db import models
from django.core.exceptions import ValidationError
from apps.trades.models import Trade
from apps.indexAndCommodity.models import Trade as IndexAndCommodityTrade
from django.db import models
from django.core.exceptions import ValidationError

class Accuracy(models.Model):
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name='accuracy')
    target_hit = models.BooleanField(default=False)
    exit_price = models.DecimalField(max_digits=10, decimal_places=2, editable=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    total_days = models.IntegerField(null=True, blank=True, help_text="Total days taken for trade completion")

    def clean(self):
        if self.trade.status != 'COMPLETED':
            raise ValidationError("Accuracy can only be updated for completed trades.")

        if self.trade.completed_at and self.trade.created_at:
            if self.trade.completed_at < self.trade.created_at:
                raise ValidationError("Completed date cannot be earlier than created date.")

    def save(self, *args, **kwargs):
        # Validate before saving
        self.full_clean()

        # Set total_days only on first creation
        if not self.pk and self.trade.completed_at:
            self.total_days = (self.trade.completed_at - self.trade.created_at).days

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Accuracy for Trade {self.trade.id} - Target Hit: {self.target_hit}"




class AccuracyOfIndexAndCommodity(models.Model):
    trade = models.ForeignKey(IndexAndCommodityTrade, on_delete=models.CASCADE,related_name='accuracy')
    exit_price = models.DecimalField(max_digits=10, decimal_places=2,editable=True, null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def clean(self):
        if self.trade.status != 'COMPLETED':
            raise ValidationError("Accuracy can only be updated for completed trades.") 
            
        

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)



