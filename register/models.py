from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from decks.models import Deck
import hashlib
import random
import datetime


class DeckRegistration(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='deck_registrations')
    deck = models.ForeignKey(
        Deck, on_delete=models.CASCADE, related_name='deck_registrations')
    verification_photo_url = models.CharField(
        max_length=255, default=None, blank=True, null=True)
    is_verified = models.BooleanField(
        default=False, verbose_name='verified')
    created_on = models.DateTimeField(auto_now_add=True)
    verified_on = models.DateTimeField(default=None, blank=True, null=True)
    verified_by = models.ForeignKey(
        User, on_delete=models.CASCADE, default=None, blank=True, null=True)


# I kinda wish there was a way to make this owrk with
class SignedNonce():
    def __init__(self, nonce, nonce_sig):
        self.nonce = nonce
        self.nonce_sig = nonce_sig

    @staticmethod
    def make_nonce():
        nonce_chars = [random.choice('0123456789ABCDEF') for _ in range(5)]
        return ''.join(nonce_chars)

    @staticmethod
    def sign(nonce):
        # A little extra security (or mabye just annoying?) signatures will
        # only be verifiable within a calendar day.
        days_since_epoch = (datetime.datetime.utcnow() -
                            datetime.datetime(1970, 1, 1)).days
        m = hashlib.sha256()
        m.update(nonce.encode())
        m.update(str(days_since_epoch).encode())
        m.update(settings.SECRET_KEY.encode())
        return m.hexdigest()

    @classmethod
    def create(cls):
        nonce = cls.make_nonce()
        nonce_sig = cls.sign(nonce)
        return cls(nonce=nonce, nonce_sig=nonce_sig)

    @classmethod
    def from_post(cls, post_data):
        return cls(post_data.get('nonce'), post_data.get('nonce_sig'))

    def is_valid(self):
        return self.nonce_sig == self.sign(self.nonce)
