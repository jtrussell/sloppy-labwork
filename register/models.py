from django.utils.translation import ugettext_lazy as _
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from decks.models import Deck
import hashlib
import random
import datetime


class DeckRegistration(models.Model):
    class Status(models.IntegerChoices):
        PENDING = 0, _('Pending')
        VERIFIED = 1, _('Verified')
        VERIFIED_ACTIVE = 2, ('Active')
        REJECTED = 3, _('Rejected')

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='deck_registrations')
    deck = models.ForeignKey(
        Deck, on_delete=models.CASCADE, related_name='deck_registrations')
    verification_code = models.CharField(max_length=5, default='?????')
    verification_photo_url = models.CharField(
        max_length=255, default=None, blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    verified_on = models.DateTimeField(default=None, blank=True, null=True)
    verified_by = models.ForeignKey(
        User, on_delete=models.CASCADE, default=None, blank=True, null=True)
    status = models.IntegerField(
        choices=Status.choices, default=Status.PENDING, blank=False, null=False)

    def __str__(self):
        return self.deck.name

    @staticmethod
    def get_active_for_user(user):
        return DeckRegistration.objects.filter(user=user, status=DeckRegistration.Status.VERIFIED_ACTIVE)

    def is_pending(self):
        return self.status == DeckRegistration.Status.PENDING

    def is_verified(self):
        return self.status == DeckRegistration.Status.VERIFIED

    def is_active(self):
        return self.status == DeckRegistration.Status.VERIFIED_ACTIVE

    def is_rejected(self):
        return self.status == DeckRegistration.Status.REJECTED

    def has_been_verified(self):
        return self.is_verified() or self.is_active()


class Meta:
    ordering = ['status', 'verified_on', 'created_on']


# I kinda wish there was a way to make this owrk with
class SignedNonce():
    def __init__(self, nonce, nonce_sig):
        self.nonce = nonce
        self.nonce_sig = nonce_sig

    @staticmethod
    def make_nonce():
        nonce_chars = [random.choice('0123456789') for _ in range(5)]
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
