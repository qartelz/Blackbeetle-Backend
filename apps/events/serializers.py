from rest_framework import serializers
from .models import Event
# class EventSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Event
#         fields = '__all__' 


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = '__all__'

    def validate(self, data):
        start_time = data.get('meeting_start_time')
        end_time = data.get('meeting_end_time')
        date = data.get('date')

        if start_time >= end_time:
            raise serializers.ValidationError("Meeting end time must be after the start time.")

        if Event.objects.filter(
            date=date,
            meeting_start_time=start_time,
            meeting_end_time=end_time
        ).exists():
            raise serializers.ValidationError("An event with the same date and time already exists.")

        return data
    
class EventSerializers(serializers.ModelSerializer):
    time = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            'id',
            'title',
            'description',
            'date',
            'platform',
            'event_link',
            'status',
            'meeting_start_time',
            'meeting_end_time',
            'created_at',
            'updated_at',
            'time',  # optional formatted start time
        ]

    def get_time(self, obj):
        return obj.meeting_start_time.strftime("%I:%M %p")