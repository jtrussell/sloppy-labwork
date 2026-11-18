from datetime import timedelta
from unittest import mock

from allauth.socialaccount.models import SocialAccount
from django.contrib.messages import get_messages
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .models import LadderChallenge, LadderEntry, LadderRuleViolation
from .tests import LadderTestBase


SIMPLE_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
WEBHOOK_URL = 'https://discord.com/api/webhooks/123456/secret-token'


class LadderHonorTestBase(LadderTestBase):
    def setUp(self):
        super().setUp()
        self.ladder.rematch_cooldown_days = 0
        self.ladder.save()

    def play(self, lower_ranked, higher_ranked, winner):
        return self.ladder.record_played_result(lower_ranked, higher_ranked, winner, winner.user)

    def defend_top_spot(self, times, champion=None, challenger=None):
        for _ in range(times):
            self.play(challenger or self.player(2), champion or self.player(1), champion or self.player(1))

    def resolve_days_ago(self, challenge, days):
        LadderChallenge.objects.filter(pk=challenge.pk).update(
            resolved_on=timezone.now() - timedelta(days=days))

    def members_honored_as(self, honor_name):
        return [
            standing.entry.member for standing in self.ladder.get_standings_for(None)
            if any(str(honor.name).startswith(honor_name) for honor in standing.honors)
        ]

    def honor_detail(self, member, honor_name):
        standing = next(
            standing for standing in self.ladder.get_standings_for(None) if standing.entry.member == member)
        return next(honor.detail for honor in standing.honors if str(honor.name).startswith(honor_name))

    def entry_for(self, member):
        return LadderEntry.objects.get(ladder=self.ladder, member=member)


class HunterOfLegendTests(LadderHonorTestBase):
    def test_nobody_is_honored_before_any_games_are_won(self):
        self.assertTrue(all(standing.honors == [] for standing in self.ladder.get_standings_for(None)))

    def test_goes_to_the_player_with_the_most_wins_challenging_up(self):
        self.play(self.player(6), self.player(5), self.player(6))
        self.play(self.player(6), self.player(4), self.player(6))
        self.play(self.player(3), self.player(2), self.player(3))
        self.assertEqual(self.members_honored_as('Hunter of Legend'), [self.player(6)])
        self.assertIn('2 wins challenging up', self.honor_detail(self.player(6), 'Hunter of Legend'))

    def test_is_shared_between_tied_leaders(self):
        self.play(self.player(6), self.player(5), self.player(6))
        self.play(self.player(3), self.player(2), self.player(3))
        self.assertEqual(self.members_honored_as('Hunter of Legend'), [self.player(3), self.player(6)])

    def test_ignores_wins_older_than_thirty_days(self):
        old_win = self.play(self.player(6), self.player(5), self.player(6))
        self.resolve_days_ago(old_win, 31)
        self.assertEqual(self.members_honored_as('Hunter of Legend'), [])

    def test_ignores_forfeit_wins(self):
        challenge = self.ladder.issue_challenge(self.player(6), self.player(5))
        self.make_overdue(challenge)
        self.ladder.resolve_overdue_challenges()
        self.assertEqual(self.members_honored_as('Hunter of Legend'), [])

    def test_ignores_voided_results(self):
        challenge = self.play(self.player(6), self.player(5), self.player(6))
        self.ladder.void_challenge(challenge, self.organizer.user)
        self.assertEqual(self.members_honored_as('Hunter of Legend'), [])

    def test_ignores_wins_from_before_the_player_rejoined(self):
        self.play(self.player(6), self.player(5), self.player(6))
        self.ladder.remove_member(self.player(6))
        self.ladder.add_member(self.player(6))
        self.assertEqual(self.members_honored_as('Hunter of Legend'), [])


class ArdentHeroTests(LadderHonorTestBase):
    def test_goes_to_the_player_with_the_most_wins_defending(self):
        self.play(self.player(4), self.player(3), self.player(3))
        self.play(self.player(5), self.player(3), self.player(3))
        self.play(self.player(2), self.player(1), self.player(1))
        self.assertEqual(self.members_honored_as('Ardent Hero'), [self.player(3)])
        self.assertEqual(self.members_honored_as('Hunter of Legend'), [])

    def test_ties_honor_nobody(self):
        self.allow_ties()
        self.ladder.record_played_result(self.player(4), self.player(3), None, self.player(4).user)
        self.assertEqual(self.members_honored_as('Ardent Hero'), [])


class RelentlessCreeperTests(LadderHonorTestBase):
    def climb(self, member, opponent):
        return self.play(member, opponent, member)

    def test_winning_records_the_ranks_climbed(self):
        challenge = self.climb(self.player(6), self.player(3))
        challenge.refresh_from_db()
        self.assertEqual((challenge.challenger_rank_before, challenge.challenger_rank_after), (6, 3))
        self.assertEqual(challenge.get_ranks_climbed(), 3)

    def test_needs_at_least_five_ranks(self):
        self.climb(self.player(6), self.player(3))
        self.climb(self.player(6), self.player(2))
        self.assertEqual(self.members_honored_as('Relentless Creeper'), [])

        self.climb(self.player(6), self.player(1))
        self.assertEqual(self.members_honored_as('Relentless Creeper'), [self.player(6)])
        self.assertIn('5 ranks climbed', self.honor_detail(self.player(6), 'Relentless Creeper'))

    def test_counts_ranks_gained_by_forfeit(self):
        self.ladder.challenge_range = 5
        self.ladder.save()
        LadderEntry.objects.filter(ladder=self.ladder).update(joined_on=timezone.now() - timedelta(days=7))
        challenge = self.ladder.issue_challenge(self.player(6), self.player(1))
        self.make_overdue(challenge)
        self.ladder.resolve_overdue_challenges()
        self.assertEqual(self.members_honored_as('Relentless Creeper'), [self.player(6)])

    def test_counts_gross_climb_after_being_moved_down(self):
        self.climb(self.player(6), self.player(3))
        self.ladder.move_member(self.player(6), 6)
        self.climb(self.player(6), self.player(3))
        self.assertEqual(self.members_honored_as('Relentless Creeper'), [self.player(6)])


class MadladTests(LadderHonorTestBase):
    def test_three_straight_defenses_of_the_top_spot_allow_ascending(self):
        self.defend_top_spot(2)
        with self.assertRaisesMessage(LadderRuleViolation, 'Mad Mab status takes 3 wins in a row'):
            self.ladder.ascend_as_madlad(self.player(1))

        self.defend_top_spot(1)
        self.ladder.ascend_as_madlad(self.player(1))

        self.assertEqual(self.ranked_usernames(), self.usernames_for(2, 3, 4, 5, 6, 1))
        self.assert_positions_contiguous()
        self.assertEqual(self.entry_for(self.player(1)).madlad_count, 1)
        self.assertEqual(self.members_honored_as('Mad Mab x1'), [self.player(1)])

    def test_defenses_of_a_lower_spot_do_not_count(self):
        self.defend_top_spot(3, champion=self.player(2), challenger=self.player(3))
        self.ladder.remove_member(self.player(1))
        self.assertEqual(self.ranked_usernames()[0], 'player2')
        with self.assertRaises(LadderRuleViolation):
            self.ladder.ascend_as_madlad(self.player(2))

    def test_only_the_top_player_can_ascend(self):
        self.defend_top_spot(3, champion=self.player(2), challenger=self.player(3))
        with self.assertRaises(LadderRuleViolation):
            self.ladder.ascend_as_madlad(self.player(2))

    def test_the_run_starts_over_after_ascending(self):
        self.defend_top_spot(3)
        self.ladder.ascend_as_madlad(self.player(1))
        self.ladder.move_member(self.player(1), 1)
        with self.assertRaises(LadderRuleViolation):
            self.ladder.ascend_as_madlad(self.player(1))

        self.defend_top_spot(3)
        self.ladder.ascend_as_madlad(self.player(1))
        self.assertEqual(self.members_honored_as('Mad Mab x2'), [self.player(1)])

    def test_ties_and_voided_defenses_do_not_count(self):
        self.allow_ties()
        self.defend_top_spot(2)
        self.ladder.record_played_result(self.player(2), self.player(1), None, self.player(1).user)
        voided = self.play(self.player(2), self.player(1), self.player(1))
        self.ladder.void_challenge(voided, self.organizer.user)
        self.assertFalse(self.ladder.can_ascend_as_madlad(self.entry_for(self.player(1))))

        self.defend_top_spot(1)
        self.assertTrue(self.ladder.can_ascend_as_madlad(self.entry_for(self.player(1))))

    def test_can_ascend_with_an_open_challenge_against_them(self):
        self.defend_top_spot(3)
        challenge = self.ladder.issue_challenge(self.player(2), self.player(1))
        self.ladder.ascend_as_madlad(self.player(1))
        challenge.refresh_from_db()
        self.assertTrue(challenge.is_pending())
        self.assertEqual(self.ranked_usernames()[-1], 'player1')

    def test_leaving_the_ladder_abandons_madlad_status(self):
        self.defend_top_spot(3)
        self.ladder.ascend_as_madlad(self.player(1))
        self.ladder.remove_member(self.player(1))
        self.ladder.add_member(self.player(1))
        self.assertEqual(self.entry_for(self.player(1)).madlad_count, 0)

    def test_not_available_when_challenges_are_disabled(self):
        self.defend_top_spot(3)
        self.ladder.challenges_enabled = False
        self.ladder.save()
        with self.assertRaises(LadderRuleViolation):
            self.ladder.ascend_as_madlad(self.player(1))


@override_settings(PMC_SITE_URL='https://keychain.example.com')
class MadladDiscordTests(LadderHonorTestBase):
    def setUp(self):
        super().setUp()
        self.ladder.discord_webhook_url = WEBHOOK_URL
        self.ladder.save()
        mock.patch(
            'pmc.discord_webhooks.run_in_background', side_effect=lambda function, *args: function(*args)).start()
        self.post = mock.patch(
            'pmc.discord_webhooks.requests.post', return_value=mock.Mock(status_code=204, text='')).start()
        self.addCleanup(mock.patch.stopall)

    def ascend_and_get_message(self):
        self.defend_top_spot(3)
        with self.captureOnCommitCallbacks(execute=True):
            self.ladder.ascend_as_madlad(self.player(1))
        return self.post.call_args_list[-1].kwargs['json']

    def test_mentions_the_champion_by_discord_id(self):
        SocialAccount.objects.create(user=self.player(1).user, provider='discord', uid='987654321')
        message = self.ascend_and_get_message()
        self.assertEqual(
            message['content'], 'The Crucible trembles. A champion ascends. Rise again, <@987654321>.')
        self.assertEqual(message['allowed_mentions'], {'parse': [], 'users': ['987654321']})
        self.assertIn('Mad Mab x1 on Main Ladder', message['embeds'][0]['title'])

    def test_names_the_champion_without_a_discord_account(self):
        message = self.ascend_and_get_message()
        self.assertEqual(
            message['content'], 'The Crucible trembles. A champion ascends. Rise again, player1.')
        self.assertEqual(message['allowed_mentions'], {'parse': [], 'users': []})


@override_settings(STORAGES=SIMPLE_STORAGES)
class LadderHonorViewTests(LadderHonorTestBase):
    def ladder_url(self, name):
        return reverse(name, args=[self.playgroup.slug, self.ladder.pk])

    def test_detail_decorates_honored_players_and_explains_the_honors(self):
        self.play(self.player(6), self.player(5), self.player(6))
        self.client.force_login(self.player(3).user)
        response = self.client.get(self.ladder_url('pmc-pg-ladder-detail'))
        self.assertContains(response, 'title="1 win challenging up in the last 30 days"')
        self.assertContains(response, 'Most wins when challenging up in the last 30 days.')
        self.assertNotContains(response, 'Most challenge wins')

    def test_go_madlad_is_offered_only_when_earned(self):
        self.client.force_login(self.player(1).user)
        response = self.client.get(self.ladder_url('pmc-pg-ladder-detail'))
        self.assertNotContains(response, 'Go Mad Mab')

        self.defend_top_spot(3)
        response = self.client.get(self.ladder_url('pmc-pg-ladder-detail'))
        self.assertContains(response, self.ladder_url('pmc-pg-ladder-madlad'))

    def test_posting_madlad_moves_the_champion_to_the_bottom(self):
        self.defend_top_spot(3)
        self.client.force_login(self.player(1).user)
        response = self.client.post(self.ladder_url('pmc-pg-ladder-madlad'))
        self.assertRedirects(response, self.ladder_url('pmc-pg-ladder-detail'))
        self.assertEqual(self.ranked_usernames()[-1], 'player1')

    def test_posting_madlad_without_earning_it_is_refused(self):
        self.client.force_login(self.player(1).user)
        response = self.client.post(self.ladder_url('pmc-pg-ladder-madlad'))
        self.assertIn('Mad Mab status takes 3 wins in a row defending the #1 spot.',
                      [str(message) for message in get_messages(response.wsgi_request)])
        self.assertEqual(self.ranked_usernames()[0], 'player1')

    def test_madlad_requires_post(self):
        self.client.force_login(self.player(1).user)
        self.assertEqual(self.client.get(self.ladder_url('pmc-pg-ladder-madlad')).status_code, 405)

    def test_all_results_page_is_paginated(self):
        for _ in range(13):
            self.play(self.player(2), self.player(1), self.player(1))
            self.play(self.player(2), self.player(1), self.player(2))
            self.play(self.player(1), self.player(2), self.player(1))
        self.client.force_login(self.player(3).user)

        detail = self.client.get(self.ladder_url('pmc-pg-ladder-detail'))
        self.assertContains(detail, self.ladder_url('pmc-pg-ladder-results'))

        first_page = self.client.get(self.ladder_url('pmc-pg-ladder-results'))
        self.assertEqual(len(first_page.context['page_obj']), 25)
        self.assertEqual(first_page.context['page_obj'].paginator.count, 39)
        self.assertContains(first_page, 'Page 1 of 2')

        second_page = self.client.get(self.ladder_url('pmc-pg-ladder-results'), {'page': 2})
        self.assertEqual(len(second_page.context['page_obj']), 14)

    def test_all_results_page_is_for_members_only(self):
        self.client.force_login(self.create_member('outsider', playgroup=self.other_playgroup()).user)
        response = self.client.get(self.ladder_url('pmc-pg-ladder-results'))
        self.assertRedirects(response, reverse('pmc-pg-detail', args=[self.playgroup.slug]))

    def other_playgroup(self):
        from .models import Playgroup
        return Playgroup.objects.create(name='Elsewhere', slug='elsewhere')
