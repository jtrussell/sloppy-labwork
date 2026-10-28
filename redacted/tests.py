from unittest import mock
from django.test import TestCase
from . import views
from .models import FallbackCollection

DECK_INFO = {'name': 'The Deck', 'url': 'https://decksofkeyforge.com/decks/abc', 'sasRating': 75}


def deck_only_for_owner(owner_with_decks):
    def get_random_deck_from_dok(filters):
        return DECK_INFO if filters['owner'] == owner_with_decks else None
    return get_random_deck_from_dok


class GetRandomDeckWithFallbackTest(TestCase):
    def setUp(self):
        FallbackCollection.objects.all().delete()
        self.filters = views.get_filters('someone', min_sas=70)

    def test_deck_from_own_collection_skips_fallback(self):
        FallbackCollection.objects.create(dok_username='vault-keeper')
        with mock.patch.object(views, 'get_random_deck_from_dok', side_effect=deck_only_for_owner('someone')) as get_deck:
            result = views.get_random_deck_with_fallback(self.filters)
        self.assertEqual(result, (DECK_INFO, None))
        self.assertEqual(get_deck.call_count, 1)

    def test_empty_collection_falls_back_with_same_filters(self):
        FallbackCollection.objects.create(dok_username='vault-keeper')
        with mock.patch.object(views, 'get_random_deck_from_dok', side_effect=deck_only_for_owner('vault-keeper')) as get_deck:
            result = views.get_random_deck_with_fallback(self.filters)
        self.assertEqual(result, (DECK_INFO, 'vault-keeper'))
        fallback_filters = get_deck.call_args.args[0]
        self.assertEqual(fallback_filters['constraints'], self.filters['constraints'])

    def test_inactive_fallback_collections_are_ignored(self):
        FallbackCollection.objects.create(dok_username='vault-keeper', is_active=False)
        with mock.patch.object(views, 'get_random_deck_from_dok', side_effect=deck_only_for_owner('vault-keeper')):
            result = views.get_random_deck_with_fallback(self.filters)
        self.assertEqual(result, (None, None))

    def test_no_fallback_collections_configured(self):
        with mock.patch.object(views, 'get_random_deck_from_dok', return_value=None):
            result = views.get_random_deck_with_fallback(self.filters)
        self.assertEqual(result, (None, None))

    def test_empty_fallback_collection(self):
        FallbackCollection.objects.create(dok_username='vault-keeper')
        with mock.patch.object(views, 'get_random_deck_from_dok', return_value=None):
            result = views.get_random_deck_with_fallback(self.filters)
        self.assertEqual(result, (None, None))
