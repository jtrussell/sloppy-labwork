from django.db import models
from django.contrib.auth.models import User
from decks.models import Deck
from io import StringIO
import csv


class Tournament(models.Model):
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='tournaments')
    name = models.CharField(max_length=200, unique=False)
    date = models.DateField()
    players_info = models.TextField()

    def parse_players_info(self):
        return self._parse_players_info(self.players_info)

    @staticmethod
    def _parse_players_info(players_info):
        infos = []
        delim = ','
        if '\t' in players_info:
            delim = '\t'
        f = StringIO(players_info)
        reader = csv.reader(f, delimiter=delim)
        for row in reader:
            if len(row) != 4:
                continue
            if row[0] == 'Discord Handle' or row[0] == 'discord_handle':
                continue
            deck_id = Deck.get_id_from_master_vault_url(row[3])
            infos.append({
                'discord_handle': row[0],
                'challonge_handle': row[1],
                'tco_handle': row[2],
                'deck_id': deck_id,
                'deck_master_vault_url': Deck.get_master_vault_ui_url_from_id(deck_id),
                'deck_dok_url': Deck.get_dok_url_from_id(deck_id)
            })
        return infos
