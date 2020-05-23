from django.db import models
from django.contrib.auth.models import User
from decks.models import Deck


class DeckRegistration(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='deck_registrations')
    deck = models.ForeignKey(
        Deck, on_delete=models.CASCADE, related_name='deck_registrations')
    photo_verification_link = models.CharField(max_length=255)
    has_photo_verification = models.BooleanField
    created_on = models.DateTimeField(auto_now_add=True)
    verified_on = models.DateTimeField()
    verified_by = models.ForeignKey(User, on_delete=models.CASCADE)
