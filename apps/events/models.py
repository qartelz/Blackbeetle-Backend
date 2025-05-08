from django.db import models
from django.core.exceptions import ValidationError

class Event(models.Model):
    PLATFORM_CHOICES = [
        ('Zoom', 'Zoom'),
        ('Meet', 'Google Meet'),
        ('Teams', 'Microsoft Teams'),
        ('Other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('upcoming', 'Upcoming'),
    ]

    date = models.DateField()
    title = models.CharField(max_length=255)
    description = models.TextField()
    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES, default='Other')
    event_link = models.URLField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='upcoming')
    meeting_start_time = models.TimeField()
    meeting_end_time = models.TimeField()

    created_at = models.DateTimeField(auto_now_add=True)  
    updated_at = models.DateTimeField(auto_now=True)      

    def __str__(self):
        return self.title
    
    def clean(self):
    # Validate end time is after start time
        if self.meeting_start_time >= self.meeting_end_time:
            raise ValidationError("Meeting end time must be after the start time.")

        # Check for overlapping events on the same date
        overlapping_events = Event.objects.filter(
            date=self.date,
            meeting_start_time=self.meeting_start_time,
            meeting_end_time=self.meeting_end_time,
        )

        if self.pk:
            overlapping_events = overlapping_events.exclude(pk=self.pk)

        if overlapping_events.exists():
            raise ValidationError("An event with the same date and time already exists.")

    # def clean(self):
    #     """Ensure meeting_end_time is after meeting_start_time."""
    #     if self.meeting_start_time >= self.meeting_end_time:
    #         raise ValidationError("Meeting end time must be after the start time.")

    def save(self, *args, **kwargs):
        """Run validation before saving."""
        self.clean()
        super().save(*args, **kwargs)
