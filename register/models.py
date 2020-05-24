from django.db import models
from django.contrib.auth.models import User
from decks.models import Deck


class DeckRegistration(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='deck_registrations')
    deck = models.ForeignKey(
        Deck, on_delete=models.CASCADE, related_name='deck_registrations')
    photo_verification_link = models.CharField(
        max_length=255, default=None, blank=True, null=True)
    has_photo_verification = models.BooleanField(
        default=False, verbose_name='verified')
    created_on = models.DateTimeField(auto_now_add=True)
    verified_on = models.DateTimeField(default=None, blank=True, null=True)
    verified_by = models.ForeignKey(
        User, on_delete=models.CASCADE, default=None, blank=True, null=True)
