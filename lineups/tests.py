import uuid

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from decks.models import Deck
from .models import Lineup, LineupVersion, LineupVersionDeck


FAST_PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
SIMPLE_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class VersionDeckSearchTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.stranger = User.objects.create_user('stranger', 'stranger@test.com', 'password')
        self.searched_version = self._create_version(self.owner, 'Searched lineup')
        self.other_version = self._create_version(self.owner, 'Other lineup')
        self.client.login(username='owner', password='password')

    def _create_version(self, owner, lineup_name):
        lineup = Lineup.objects.create(owner=owner, name=lineup_name)
        return LineupVersion.objects.create(lineup=lineup, name='First version')

    def _add_deck(self, version, deck_name):
        deck = Deck.objects.create(id=uuid.uuid4(), name=deck_name)
        LineupVersionDeck.objects.create(version=version, deck=deck)
        return deck

    def _search(self, name_query):
        return self.client.get(
            reverse('lineups-version-deck-search', args=[self.searched_version.code]),
            {'deck_input': name_query})

    def test_search_lists_matching_decks_from_other_own_lineups(self):
        self._add_deck(self.other_version, 'Bumblebird the Bold')
        self._add_deck(self.other_version, 'Quiet Archivist')
        self._add_deck(self.searched_version, 'Bumblebird Already Here')
        self._add_deck(self._create_version(self.stranger, 'Stranger lineup'), 'Bumblebird the Stranger')

        response = self._search('BUMBLE')

        self.assertContains(response, '<option value="Bumblebird the Bold"></option>', html=True)
        self.assertContains(response, '<option', count=1)

    def test_search_escapes_deck_names(self):
        self._add_deck(self.other_version, 'Bumble"><script>alert(1)</script> & "Sons"')

        response = self._search('bumble')

        self.assertNotContains(response, '<script>')
        self.assertContains(
            response,
            'value="Bumble&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;Sons&quot;"')

    def test_search_is_empty_for_short_queries_and_links(self):
        self._add_deck(self.other_version, 'Bumblebird')

        for name_query in ['b', '', 'https://decksofkeyforge.com/decks/bumblebird']:
            response = self._search(name_query)
            self.assertNotContains(response, '<option')

    def test_search_is_forbidden_for_other_users(self):
        self.client.login(username='stranger', password='password')

        response = self._search('bumble')

        self.assertEqual(response.status_code, 403)
