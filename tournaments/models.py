from django.db import models
from django.urls import reverse
from django.contrib.auth.models import User
from decks.models import Deck
from register.models import DeckRegistration
from io import StringIO
import csv


class TournamentFormat(models.Model):
    name = models.CharField(max_length=200, unique=False)
    decks_per_player = models.IntegerField(default=1)

    def __str__(self):
        return self.name


class Tournament(models.Model):
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='tournaments')
    name = models.CharField(max_length=200, unique=False)
    date = models.DateField()
    tournament_format = models.ForeignKey(
        TournamentFormat, on_delete=models.CASCADE, related_name='tournaments')

    def get_sign_up_url(self):
        return reverse('tournaments-register', kwargs={'pk': self.id})


class TournamentRegistration(models.Model):
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name='tournament_registrations')
    player = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='tournament_registrations')
    decks = models.ManyToManyField(
        Deck, related_name='tournament_registrations')

    def are_decks_verified(self):
        self_decks = self.decks.all()
        registrations = DeckRegistration.objects.filter(
            deck__in=self_decks, is_active=True, is_verified=True)
        return registrations.count() == len(self_decks)
