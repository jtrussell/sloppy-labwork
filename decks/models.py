import json
from django.db import models
from requests import get


class Deck(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=200, unique=True)
    expansion = models.IntegerField(null=True)
    house1 = models.CharField(null=True, max_length=50)
    house2 = models.CharField(null=True, max_length=50)
    house3 = models.CharField(null=True, max_length=50)
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

    def fetch_master_vault_data_and_save(self):
        r = get(self.get_master_vault_api_url())
        json = r.json()
        self.name = json['data']['name']
        self.expansion = json['data']['expansion']
        self.house1 = json['data']['_links']['houses'][0]
        self.house2 = json['data']['_links']['houses'][1]
        self.house3 = json['data']['_links']['houses'][2]
        self.save()
        return self

    def __str__(self):
        return self.name
