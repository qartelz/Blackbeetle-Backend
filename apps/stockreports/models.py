from django.db import models

class StockReport(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PUBLISHED = 'PUBLISHED', 'Published'
        ARCHIVED = 'ARCHIVED', 'Archived'

    class Strategy(models.TextChoices):
        POSITIONAL = 'POSITIONAL', 'Positional'
        INTRADAY = 'INTRADAY', 'Intraday'
        BTST = 'BTST', 'BTST'

    title = models.CharField(max_length=255)
    date_created = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    strategy = models.CharField(
        max_length=20,
        choices=Strategy.choices
    )
    pdf_upload = models.FileField(upload_to='stockreports/pdfs/', null=True, blank=True)

    def __str__(self):
        return self.title