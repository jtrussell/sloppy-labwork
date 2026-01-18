from django.contrib.auth.models import User
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _


def generate_lineup_code():
    length = 6
    while True:
        code = 'lnp_' + get_random_string(
            length, allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        if not Lineup.objects.filter(code=code).exists():
            return code


def generate_lineup_version_code():
    length = 6
    while True:
        code = 'lnpv_' + get_random_string(
            length, allowed_chars='0123456789')
        if not LineupVersion.objects.filter(code=code).exists():
            return code


class Lineup(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = 'private', _('Private')
        UNLISTED = 'unlisted', _('Unlisted')
        PUBLIC = 'public', _('Public')

    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='lineups')
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(default=None, null=True, blank=True)
    visibility = models.CharField(
        max_length=10, choices=Visibility.choices, default=Visibility.PRIVATE)
    format = models.ForeignKey(
        'pmc.EventFormat', on_delete=models.SET_NULL,
        related_name='lineups', default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_on']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generate_lineup_code()
        super().save(*args, **kwargs)

    def can_view(self, user):
        if user.is_authenticated and self.owner == user:
            return True
        if self.visibility == self.Visibility.PUBLIC:
            return True
        if self.visibility == self.Visibility.UNLISTED:
            return True
        return False

    def can_edit(self, user):
        return user.is_authenticated and self.owner == user

    def get_visible_versions(self, user):
        if user.is_authenticated and self.owner == user:
            return self.versions.all()
        return self.versions.filter(
            models.Q(visibility_override__isnull=True) |
            models.Q(visibility_override=LineupVersion.Visibility.PUBLIC)
        )

    @property
    def latest_version(self):
        return self.versions.order_by('-sort_order').first()


class LineupNote(models.Model):
    lineup = models.ForeignKey(
        Lineup, on_delete=models.CASCADE, related_name='notes')
    text = models.TextField()
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_on']

    def __str__(self):
        return f'Note on {self.lineup.name}'


class LineupVersion(models.Model):
    class Visibility(models.TextChoices):
        UNLISTED = 'unlisted', _('Unlisted')
        PUBLIC = 'public', _('Public')

    lineup = models.ForeignKey(
        Lineup, on_delete=models.CASCADE, related_name='versions')
    code = models.CharField(max_length=11, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(default=None, null=True, blank=True)
    visibility_override = models.CharField(
        max_length=10, choices=Visibility.choices,
        default=None, null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_on']

    def __str__(self):
        return f'{self.lineup.name} - {self.name}'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generate_lineup_version_code()
        super().save(*args, **kwargs)

    def get_effective_visibility(self):
        if self.visibility_override:
            return self.visibility_override
        return self.lineup.visibility

    def can_view(self, user):
        if user.is_authenticated and self.lineup.owner == user:
            return True
        effective = self.get_effective_visibility()
        return effective in [Lineup.Visibility.PUBLIC, Lineup.Visibility.UNLISTED]


class LineupVersionNote(models.Model):
    version = models.ForeignKey(
        LineupVersion, on_delete=models.CASCADE, related_name='notes')
    text = models.TextField()
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_on']

    def __str__(self):
        return f'Note on {self.version.name}'


class LineupVersionDeck(models.Model):
    version = models.ForeignKey(
        LineupVersion, on_delete=models.CASCADE, related_name='version_decks')
    deck = models.ForeignKey(
        'decks.Deck', on_delete=models.CASCADE, related_name='lineup_versions')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['version', 'deck'],
                name='unique_version_deck')
        ]

    def __str__(self):
        return f'{self.version.name} - {self.deck.name}'
