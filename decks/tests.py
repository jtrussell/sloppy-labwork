from django.test import TestCase

from .models import Set


class SetShortNameTest(TestCase):
    def test_blank_short_name_defaults_to_full_name(self):
        deck_set = Set.objects.create(id=907, name='Discovery', src='https://example.com/d.png')
        self.assertEqual(deck_set.short_name, 'Discovery')

    def test_given_short_name_is_kept(self):
        deck_set = Set.objects.create(
            id=341, name='Call of the Archons', short_name='CotA', src='https://example.com/c.png')
        self.assertEqual(deck_set.short_name, 'CotA')
