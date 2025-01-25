from django.db import models
from django.db.models import UniqueConstraint
from datetime import date


class Playgroup(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    events = models.ManyToManyField(
        'Event', through='PlaygroupEvent', related_name='playgroups'
    )

    class Meta:
        ordering = ['-name']

    def __str__(self):
        return self.name


class PlaygroupMember(models.Model):
    playgroup = models.ForeignKey(
        Playgroup, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    nickname = models.CharField(
        max_length=100, default=None, null=True, blank=True)
    joined_on = models.DateTimeField(auto_now_add=True)
    is_staff = models.BooleanField(default=False)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['playgroup', 'user'],
                             name='unique_playgroup_member'),
            UniqueConstraint(fields=['playgroup', 'nickname'],
                             name='unique_playgroup_member_nickname'),
        ]

    def __str__(self):
        return f'{self.nickname} ({self.user.username})' if self.nickname else self.user.username


class Event(models.Model):
    name = models.CharField(max_length=200)
    start_date = models.DateField(default=date.today)

    class Meta:
        ordering = ('-start_date',)

    def __str__(self):
        return f'{self.name} ({self.start_date})'


class PlaygroupEvent(models.Model):
    playgroup = models.ForeignKey(
        Playgroup, on_delete=models.CASCADE, related_name='playgroup_events')
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name='playgroup_events')

    class Meta:
        unique_together = ('playgroup', 'event',)


class EventResult(models.Model):
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name='results')
    user = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE, related_name='event_results')
    finishing_position = models.PositiveSmallIntegerField(
        default=None, null=True, blank=True)
    num_wins = models.PositiveSmallIntegerField(
        default=None, null=True, blank=True)
    num_losses = models.PositiveSmallIntegerField(
        default=None, null=True, blank=True)

    class Meta:
        ordering = ('finishing_position', '-num_wins', 'num_losses',)
