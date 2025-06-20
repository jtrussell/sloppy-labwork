from django.db import models
from requests import get
from django.utils.translation import gettext_lazy as _

EXPANSION_CHOICES = [
    (None, _('Any')),
    (341, _('Call of the Archons')),
    (435, _('Age of Ascension')),
    (452, _('Worlds Collide')),
    (479, _('Mass Mutation')),
    (496, _('Dark Tidings')),
    (600, _('Winds of Exchange')),
    (601, _('Unchained 2022')),
    (609, _('Vault Masters 2023')),
    (700, _('Grim Reminders')),
    (722, _('Menagerie')),
    (737, _('Vault Masters 2024')),
    (800, _('Æmber Skies')),
    (855, _('Tokens of Change')),
    (874, _('More Mutation')),
    (886, _('Prophetic Visions')),
    (907, _('Discovery')),
    (918, _('Crucible Clash')),
]


class Deck(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=200, unique=True)
    set = models.SmallIntegerField(
        default=None, null=True, blank=True, choices=EXPANSION_CHOICES)
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

    def set_display(self):
        return dict(EXPANSION_CHOICES).get(self.set, _('Unknown'))

    def __str__(self):
        return self.name
