from datetime import timedelta
from enum import Enum

from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string


def generate_timer_code():
    length = 6
    while True:
        code = get_random_string(
            length, allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        if not CountdownTimer.objects.filter(code=code).exists():
            return code


class TimerState(Enum):
    ACTIVE = 'active'
    PAUSED = 'paused'


class CountdownTimer(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=6, unique=True)
    owner = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE, blank=True, null=True)
    end_time = models.DateTimeField(default=None, blank=True, null=True)
    pause_time_remaining_seconds = models.IntegerField(
        default=None, blank=True, null=True)
    original_duration_seconds = models.IntegerField(
        default=None, blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generate_timer_code()
        super().save(*args, **kwargs)

    def pause(self):
        if self.pause_time_remaining_seconds is not None:
            return

        if self.end_time is None:
            return

        remaining = (self.end_time - timezone.now()).total_seconds()
        self.pause_time_remaining_seconds = max(0, int(remaining))
        self.end_time = None
        self.save()

    def start(self):
        if self.pause_time_remaining_seconds is None:
            return

        self.end_time = timezone.now() + timedelta(
            seconds=self.pause_time_remaining_seconds
        )
        self.pause_time_remaining_seconds = None
        self.save()

    def is_expired(self):
        if self.pause_time_remaining_seconds is not None:
            return self.pause_time_remaining_seconds <= 0
        if self.end_time is not None:
            return self.end_time <= timezone.now()
        return True

    def add_seconds(self, num_seconds):
        if self.pause_time_remaining_seconds is not None:
            self.pause_time_remaining_seconds += num_seconds
        elif self.end_time is not None:
            if self.is_expired():
                self.end_time = timezone.now() + timedelta(seconds=num_seconds)
            else:
                self.end_time += timedelta(seconds=num_seconds)
        self.save()

    def subtract_seconds(self, num_seconds):
        if self.pause_time_remaining_seconds is not None:
            self.pause_time_remaining_seconds = max(
                0, self.pause_time_remaining_seconds - num_seconds
            )
        elif self.end_time is not None:
            self.end_time -= timedelta(seconds=num_seconds)
        self.save()

    def set_time_remaining_seconds(self, num_seconds):
        if self.pause_time_remaining_seconds is not None:
            self.pause_time_remaining_seconds = num_seconds
        elif self.end_time is not None:
            self.end_time = timezone.now() + timedelta(seconds=num_seconds)
        self.save()

    def reset(self):
        if self.original_duration_seconds is None:
            return

        self.pause_time_remaining_seconds = self.original_duration_seconds
        self.end_time = None
        self.save()

    def get_state(self):
        if self.pause_time_remaining_seconds is not None:
            return TimerState.PAUSED
        if self.end_time is not None:
            return TimerState.ACTIVE
        return TimerState.PAUSED
