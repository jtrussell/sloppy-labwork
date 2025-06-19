from django.db import models
from requests import get


class Deck(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=200, unique=True)
    set = models.SmallIntegerField()
    added_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    @staticmethod
    def get_id_from_master_vault_url(value):
        return value.strip().rsplit('/', 1)[-1]

    @staticmethod
    def get_master_vault_ui_url_from_id(value):
        return 'https://www.keyforgegame.com/deck-details/{}'.format(value)

    @staticmethod
    def get_master_vault_api_url_from_id(value):
        return 'https://www.keyforgegame.com/api/decks/{}/'.format(value)

    @staticmethod
    def get_dok_url_from_id(value):
        return 'https://decksofkeyforge.com/decks/{}'.format(value)

    def get_master_vault_api_url(self):
        return self.get_master_vault_api_url_from_id(self.id)

    def get_dok_url(self):
        return self.get_dok_url_from_id(self.id)

    def hydrate_from_master_vault(self, save=True):
        r = get(self.get_master_vault_api_url())
        if r.status_code == 200:
            data = r.json()
            self.name = data['name']
            self.set = data['expansion']
            if save:
                self.save()
        else:
            raise ValueError(
                f'Failed to fetch deck data: {r.status_code} {r.reason}')

    def __str__(self):
        return self.name
