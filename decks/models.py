import random
from django.db import models
from requests import get, head
from django.utils.translation import gettext_lazy as _


class Set(models.Model):
    id = models.SmallIntegerField(primary_key=True)
    name = models.CharField(max_length=200, unique=True)
    src = models.URLField()

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class House(models.Model):
    mv_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    name = models.CharField(max_length=200, unique=True)
    src = models.URLField()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Deck(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=200, unique=True)
    added_on = models.DateTimeField(auto_now_add=True)

    set = models.ForeignKey(
        Set, on_delete=models.SET_NULL, null=True, blank=True, related_name='decks')
    house_1 = models.ForeignKey(
        House, on_delete=models.SET_NULL, null=True, blank=True, related_name='decks_house_1')
    house_2 = models.ForeignKey(
        House, on_delete=models.SET_NULL, null=True, blank=True, related_name='decks_house_2')
    house_3 = models.ForeignKey(
        House, on_delete=models.SET_NULL, null=True, blank=True, related_name='decks_house_3')

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

    def get_mv_url(self):
        return self.get_master_vault_ui_url_from_id(self.id)

    def hydrate_from_master_vault(self, save=True):
        r = get(self.get_master_vault_api_url(), headers={
                'X-Forwarded-For': '192.168.{}.{}'.format(
                    random.randint(1, 255),
                    random.randint(1, 255)
                )})
        if r.status_code == 200:
            data = r.json()['data']
            houses = data['_links']['houses']
            self.name = data['name']
            self.set = Set.objects.get(id=data['expansion'])
            self.house_1 = House.objects.get(
                mv_id=houses[0]) if len(houses) > 0 else None
            self.house_2 = House.objects.get(
                mv_id=houses[1]) if len(houses) > 1 else None
            self.house_3 = House.objects.get(
                mv_id=houses[2]) if len(houses) > 2 else None
            if save:
                self.save()
        else:
            raise ValueError(
                f'Failed to fetch deck data: {r.status_code} {r.reason}')

    def __str__(self):
        return self.name
