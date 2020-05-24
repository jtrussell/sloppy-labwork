from django.db import models
from django.contrib.auth.models import User


class Deck(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=200, unique=True)
    added_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    @staticmethod
    def get_id_from_master_vault_url(value):
        return value.strip().rsplit('/', 1)[-1]

    def get_master_vault_url(self):
        return 'https://www.keyforgegame.com/api/decks/{}/'.format(self.id)

    def get_dok_url(self):
        return 'https://decksofkeyforge.com/decks/{}'.format(self.id)

    def __str__(self):
        return self.name
