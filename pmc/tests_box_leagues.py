from datetime import date
from itertools import combinations

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    BoxLeague, BoxLeagueRuleViolation, BoxLeagueSession, BoxMatch, Feature, Match,
    Playgroup, PlaygroupFeature, PlaygroupMember,
)


SIMPLE_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


class BoxLeagueTestBase(TestCase):
    def setUp(self):
        self.playgroup = Playgroup.objects.create(name='Box Group', slug='box-group')
        self.enable_box_leagues_for(self.playgroup)
        self.organizer = self.create_member('organizer', is_staff=True)
        self.players = [self.create_member(f'player{number}') for number in range(1, 10)]
        self.league = BoxLeague.objects.create(
            playgroup=self.playgroup, name='Winter League', target_box_size=3)
        self.league.rename_tiers(['Gold', 'Silver', 'Bronze'])
        for player in self.players:
            self.league.join(player)

    def use_pyramid(self):
        self.league.layout = BoxLeague.Layouts.PYRAMID
        self.league.save()

    def enable_box_leagues_for(self, playgroup):
        PlaygroupFeature.objects.create(
            playgroup=playgroup, feature=Feature.objects.get(key=Feature.Keys.BOX_LEAGUES))

    def create_member(self, username, playgroup=None, is_staff=False):
        return PlaygroupMember.objects.create(
            playgroup=playgroup or self.playgroup,
            user=User.objects.create_user(username=username),
            is_staff=is_staff,
        )

    def player(self, number):
        return self.players[number - 1]

    def start_next_session(self):
        if self.league.get_proposed_session() is None:
            self.league.plan_next_session()
        return self.league.start_session(date(2026, 10, 1), date(2026, 11, 1))

    def summary_named(self, session, name):
        return next(summary for summary in session.get_box_summaries() if summary.name == name)

    def usernames_in(self, session, name):
        return [standing.member.user.username for standing in self.summary_named(session, name).standings]

    def box_names_by_username(self, session):
        return {
            standing.member.user.username: summary.name
            for summary in session.get_box_summaries()
            for standing in summary.standings
        }

    def box_match_between(self, session, first, second):
        return BoxMatch.objects.select_related('match__player_one', 'match__player_two').get(
            box__session=session,
            match__player_one__in=[first, second],
            match__player_two__in=[first, second],
        )

    def record(self, session, winner, loser):
        self.league.record_result(self.box_match_between(session, winner, loser), winner, winner.user)

    def play_out(self, session, ranked_players):
        for stronger, weaker in combinations(ranked_players, 2):
            self.record(session, stronger, weaker)


class BoxLeagueTierTests(BoxLeagueTestBase):
    def test_unnamed_tiers_get_default_names(self):
        self.league.rename_tiers(['', 'Silver'])
        proposal = self.league.plan_next_session()
        self.assertEqual(
            [summary.name for summary in proposal.get_box_summaries()], ['Tier 1', 'Silver', 'Tier 3'])

    def test_pyramid_boxes_are_lettered_within_a_tier(self):
        self.use_pyramid()
        proposal = self.league.plan_next_session()
        self.assertEqual(
            [summary.name for summary in proposal.get_box_summaries()],
            ['Gold', 'Silver A', 'Silver B'])

    def test_renaming_a_tier_renames_existing_boxes(self):
        session = self.start_next_session()
        self.league.rename_tiers(['Diamond', 'Silver', 'Bronze'])
        self.assertEqual(set(self.usernames_in(session, 'Diamond')), {'player1', 'player2', 'player3'})

    def test_unplayed_active_boxes_order_players_reproducibly(self):
        session = self.start_next_session()
        self.assertEqual(self.usernames_in(session, 'Gold'), self.usernames_in(session, 'Gold'))

    def test_suggested_end_date_respects_month_lengths(self):
        self.assertEqual(self.league.suggested_end_date(date(2026, 1, 31)), date(2026, 2, 28))
        self.assertEqual(self.league.suggested_end_date(date(2026, 12, 15)), date(2027, 1, 15))
        self.league.session_length_months = 3
        self.assertEqual(self.league.suggested_end_date(date(2026, 11, 30)), date(2027, 2, 28))


class BoxLeagueLifecycleTests(BoxLeagueTestBase):
    def test_first_proposal_places_players_in_join_order(self):
        proposal = self.league.plan_next_session()
        self.assertTrue(proposal.is_proposed())
        self.assertEqual(proposal.number, 1)
        self.assertEqual(self.usernames_in(proposal, 'Gold'), ['player1', 'player2', 'player3'])
        self.assertEqual(self.usernames_in(proposal, 'Bronze'), ['player7', 'player8', 'player9'])
        self.assertFalse(Match.objects.exists())

    def test_only_one_proposal_at_a_time(self):
        self.league.plan_next_session()
        with self.assertRaisesMessage(BoxLeagueRuleViolation, 'already proposed'):
            self.league.plan_next_session()

    def test_starting_creates_every_pairing_in_each_box(self):
        session = self.start_next_session()
        self.assertTrue(session.is_active())
        self.assertEqual(session.starts_on, date(2026, 10, 1))
        self.assertEqual(BoxMatch.objects.filter(box__session=session).count(), 9)

    def test_starting_the_next_session_completes_the_previous_one(self):
        first_session = self.start_next_session()
        second_session = self.start_next_session()
        first_session.refresh_from_db()
        self.assertTrue(first_session.is_completed())
        self.assertTrue(second_session.is_active())
        self.assertEqual(second_session.number, 2)

    def test_session_cannot_end_before_it_starts(self):
        self.league.plan_next_session()
        with self.assertRaisesMessage(BoxLeagueRuleViolation, 'end on or after'):
            self.league.start_session(date(2026, 10, 2), date(2026, 10, 1))

    def test_starting_requires_placed_players_and_drops_empty_boxes(self):
        empty_league = BoxLeague.objects.create(playgroup=self.playgroup, name='Empty League')
        empty_league.plan_next_session()
        with self.assertRaisesMessage(BoxLeagueRuleViolation, 'Place at least one player'):
            empty_league.start_session(date(2026, 10, 1), date(2026, 11, 1))

        proposal = self.league.plan_next_session()
        for player in self.players[3:]:
            self.league.remove_from_session(player, proposal)
        session = self.league.start_session(date(2026, 10, 1), date(2026, 11, 1))
        self.assertEqual([summary.name for summary in session.get_box_summaries()], ['Gold'])

    def test_database_allows_one_proposed_session_per_league(self):
        self.league.plan_next_session()
        with self.assertRaises(IntegrityError), transaction.atomic():
            BoxLeagueSession.objects.create(
                league=self.league, number=99, status=BoxLeagueSession.SessionStatuses.PROPOSED)

    def test_discarding_a_proposal(self):
        self.league.plan_next_session()
        self.league.discard_proposal()
        self.assertFalse(BoxLeagueSession.objects.exists())

    def test_sessions_link_backwards_and_forwards(self):
        first_session = self.start_next_session()
        second_session = self.start_next_session()
        proposal = self.league.plan_next_session()
        self.assertIsNone(first_session.get_previous_session())
        self.assertEqual(first_session.get_next_session(), second_session)
        self.assertEqual(second_session.get_previous_session(), first_session)
        self.assertEqual(second_session.get_next_session(), proposal)
        self.assertIsNone(proposal.get_next_session())


class BoxLeagueMovementTests(BoxLeagueTestBase):
    def setUp(self):
        super().setUp()
        self.session = self.start_next_session()
        self.play_out(self.session, [self.player(1), self.player(2), self.player(3)])
        self.play_out(self.session, [self.player(4), self.player(5), self.player(6)])
        self.play_out(self.session, [self.player(7), self.player(8), self.player(9)])

    def test_standings_mark_promotion_and_relegation_zones(self):
        gold = self.summary_named(self.session, 'Gold')
        silver = self.summary_named(self.session, 'Silver')
        bronze = self.summary_named(self.session, 'Bronze')
        self.assertEqual([standing.points for standing in gold.standings], [4, 2, 0])
        self.assertEqual([standing.is_relegated for standing in gold.standings], [False, False, True])
        self.assertFalse(any(standing.is_promoted for standing in gold.standings))
        self.assertEqual([standing.is_promoted for standing in silver.standings], [True, False, False])
        self.assertEqual([standing.is_relegated for standing in silver.standings], [False, False, True])
        self.assertEqual([standing.is_promoted for standing in bronze.standings], [True, False, False])
        self.assertFalse(any(standing.is_relegated for standing in bronze.standings))

    def test_next_session_promotes_and_relegates_one_per_box(self):
        proposal = self.league.plan_next_session()
        self.assertEqual(self.usernames_in(proposal, 'Gold'), ['player1', 'player2', 'player4'])
        self.assertEqual(self.usernames_in(proposal, 'Silver'), ['player3', 'player5', 'player7'])
        self.assertEqual(self.usernames_in(proposal, 'Bronze'), ['player6', 'player8', 'player9'])

    def test_layout_changes_apply_to_the_next_proposal(self):
        self.use_pyramid()
        proposal = self.league.plan_next_session()
        self.assertEqual(
            [summary.name for summary in proposal.get_box_summaries()], ['Gold', 'Silver A', 'Silver B'])


class BoxLeagueSizingTests(BoxLeagueTestBase):
    def test_box_count_follows_the_target_box_size(self):
        self.assertEqual(self.league.suggested_box_count(9), 3)
        self.assertEqual(self.league.suggested_box_count(1), 1)
        self.league.target_box_size = 5
        self.assertEqual(self.league.suggested_box_count(100), 20)

    def test_a_growing_league_gets_more_boxes(self):
        self.start_next_session()
        for number in range(10, 16):
            self.league.join(self.create_member(f'player{number}'))
        proposal = self.league.plan_next_session()
        self.assertEqual(len(proposal.get_box_summaries()), 5)

    def test_pyramid_shape_scales_with_players(self):
        self.use_pyramid()
        for number in range(10, 22):
            self.league.join(self.create_member(f'player{number}'))
        proposal = self.league.plan_next_session()
        self.assertEqual(
            [summary.name for summary in proposal.get_box_summaries()],
            ['Gold', 'Silver A', 'Silver B', 'Bronze A', 'Bronze B', 'Bronze C', 'Bronze D'])

    def test_resizing_a_proposal_keeps_its_players_and_survives_rebalance(self):
        proposal = self.league.plan_next_session()
        self.league.resize_proposal(2)
        self.assertEqual(len(proposal.get_box_summaries()), 2)
        self.assertEqual(len(self.box_names_by_username(proposal)), 9)
        for number in range(1, 10):
            self.league.confirm(self.player(number))
        self.league.rebalance_proposal()
        self.assertEqual(len(proposal.get_box_summaries()), 2)

    def test_resizing_keeps_players_removed_from_the_proposal_out(self):
        proposal = self.league.plan_next_session()
        self.league.remove_from_session(self.player(9), proposal)
        self.league.resize_proposal(4)
        self.assertNotIn('player9', self.box_names_by_username(proposal))

    def test_adding_and_removing_boxes_mid_session(self):
        session = self.start_next_session()
        added_box = self.league.add_box(session, 2)
        self.assertEqual(
            [summary.name for summary in session.get_box_summaries()],
            ['Gold', 'Silver A', 'Silver B', 'Bronze'])
        self.league.remove_box(added_box)
        self.assertEqual(len(session.get_box_summaries()), 3)

    def test_new_bottom_tier_and_level_limits(self):
        session = self.start_next_session()
        self.league.add_box(session, 4)
        self.assertEqual(session.get_box_summaries()[-1].name, 'Tier 4')
        with self.assertRaisesMessage(BoxLeagueRuleViolation, 'existing tier or a new bottom tier'):
            self.league.add_box(session, 7)

    def test_boxes_with_players_cannot_be_removed(self):
        session = self.start_next_session()
        with self.assertRaisesMessage(BoxLeagueRuleViolation, 'Move everyone out'):
            self.league.remove_box(self.summary_named(session, 'Gold').box)


class BoxLeaguePyramidMovementTests(BoxLeagueTestBase):
    def test_top_box_sends_two_down_and_each_lower_box_sends_one_up(self):
        self.use_pyramid()
        session = self.start_next_session()
        self.assertEqual(set(self.usernames_in(session, 'Silver A')), {'player4', 'player7', 'player8'})
        self.play_out(session, [self.player(1), self.player(2), self.player(3)])
        self.play_out(session, [self.player(4), self.player(7), self.player(8)])
        self.play_out(session, [self.player(5), self.player(6), self.player(9)])

        gold = self.summary_named(session, 'Gold')
        self.assertEqual([standing.is_relegated for standing in gold.standings], [False, True, True])

        proposal = self.league.plan_next_session()
        self.assertEqual(set(self.usernames_in(proposal, 'Gold')), {'player1', 'player4', 'player5'})


class BoxLeagueConfirmationTests(BoxLeagueTestBase):
    def setUp(self):
        super().setUp()
        self.session = self.start_next_session()
        self.proposal = self.league.plan_next_session()

    def test_rebalance_excludes_unconfirmed_players(self):
        for number in range(1, 9):
            self.league.confirm(self.player(number))
        self.league.rebalance_proposal()
        box_names = self.box_names_by_username(self.proposal)
        self.assertNotIn('player9', box_names)
        self.assertEqual(len(box_names), 8)
        self.assertEqual(
            [len(summary.standings) for summary in self.proposal.get_box_summaries()], [3, 3, 2])

    def test_joining_during_a_proposal_confirms_and_places_in_the_bottom_tier(self):
        newcomer = self.create_member('newcomer')
        self.league.join(newcomer)
        self.assertIn(newcomer.pk, self.proposal.get_confirmed_member_ids())
        self.assertEqual(self.box_names_by_username(self.proposal)['newcomer'], 'Bronze')

    def test_removing_from_a_proposal_survives_a_rebalance(self):
        for number in range(1, 10):
            self.league.confirm(self.player(number))
        self.league.remove_from_session(self.player(2), self.proposal)
        self.league.rebalance_proposal()
        self.assertNotIn('player2', self.box_names_by_username(self.proposal))

    def test_proposal_goes_stale_when_boxes_change_mid_session(self):
        bronze = self.summary_named(self.session, 'Bronze').box
        self.league.assign_to_box(self.player(1), bronze)
        self.assertTrue(self.proposal.is_stale_proposal())

    def test_withdrawing_a_confirmation(self):
        self.league.confirm(self.player(1))
        self.league.withdraw_confirmation(self.player(1))
        self.assertNotIn(self.player(1).pk, self.proposal.get_confirmed_member_ids())

    def test_confirming_requires_a_proposal_and_roster_spot(self):
        outsider = self.create_member('outsider')
        with self.assertRaisesMessage(BoxLeagueRuleViolation, 'Join the league first'):
            self.league.confirm(outsider)
        self.league.discard_proposal()
        with self.assertRaisesMessage(BoxLeagueRuleViolation, 'no proposed session'):
            self.league.confirm(self.player(1))

    def test_proposal_goes_stale_when_results_change(self):
        self.assertFalse(self.proposal.is_stale_proposal())
        self.record(self.session, self.player(1), self.player(2))
        self.assertTrue(self.proposal.is_stale_proposal())
        self.league.rebalance_proposal()
        self.proposal.refresh_from_db()
        self.assertFalse(self.proposal.is_stale_proposal())

    def test_placing_a_player_in_the_proposal_confirms_them(self):
        bronze = self.summary_named(self.proposal, 'Bronze').box
        self.league.assign_to_box(self.player(1), bronze)
        self.assertEqual(self.box_names_by_username(self.proposal)['player1'], 'Bronze')
        self.assertIn(self.player(1).pk, self.proposal.get_confirmed_member_ids())


class BoxLeagueMidSessionTests(BoxLeagueTestBase):
    def setUp(self):
        super().setUp()
        self.session = self.start_next_session()
        self.record(self.session, self.player(1), self.player(3))
        self.silver = self.summary_named(self.session, 'Silver').box
        self.gold = self.summary_named(self.session, 'Gold').box

    def matches_involving(self, member):
        return Match.objects.filter(box_match__box__session=self.session).filter(
            player_one=member) | Match.objects.filter(
            box_match__box__session=self.session).filter(player_two=member)

    def test_moving_keeps_played_results_and_replaces_unplayed_matches(self):
        self.league.assign_to_box(self.player(3), self.silver)

        self.assertTrue(Match.objects.filter(pk=self.box_match_between(
            self.session, self.player(1), self.player(3)).match_id).exists())
        self.assertFalse(BoxMatch.objects.filter(
            box=self.gold, match__player_one__in=[self.player(2), self.player(3)],
            match__player_two__in=[self.player(2), self.player(3)]).exists())
        self.assertEqual(BoxMatch.objects.filter(box=self.silver).count(), 6)

        gold_standings = self.summary_named(self.session, 'Gold').standings
        self.assertEqual([standing.member for standing in gold_standings], [self.player(1), self.player(2)])
        self.assertEqual(gold_standings[0].played, 0)

    def test_moving_back_does_not_duplicate_played_pairings(self):
        self.league.assign_to_box(self.player(3), self.silver)
        self.league.assign_to_box(self.player(3), self.gold)
        self.assertEqual(self.matches_involving(self.player(3)).count(), 2)
        self.assertEqual(BoxMatch.objects.filter(box=self.silver).count(), 3)

    def test_pair_moved_together_keeps_their_result(self):
        self.league.assign_to_box(self.player(1), self.silver)
        self.league.assign_to_box(self.player(3), self.silver)
        silver_standings = self.summary_named(self.session, 'Silver').standings
        winner_standing = next(standing for standing in silver_standings if standing.member == self.player(1))
        self.assertEqual((winner_standing.played, winner_standing.points), (1, 2))

    def test_adding_a_new_player_into_a_box_creates_their_matches(self):
        newcomer = self.create_member('newcomer')
        bronze = self.summary_named(self.session, 'Bronze').box
        self.league.assign_to_box(newcomer, bronze)
        self.assertTrue(self.league.is_on_roster(newcomer))
        self.assertEqual(BoxMatch.objects.filter(box=bronze).count(), 6)

    def test_removing_from_a_session_keeps_them_waiting_on_the_roster(self):
        self.league.remove_from_session(self.player(3), self.session)
        self.assertNotIn('player3', self.box_names_by_username(self.session))
        self.assertEqual(self.matches_involving(self.player(3)).count(), 1)
        self.assertTrue(self.league.is_on_roster(self.player(3)))

    def test_leaving_removes_from_roster_session_and_proposal(self):
        proposal = self.league.plan_next_session()
        self.league.leave(self.player(5))
        self.assertFalse(self.league.is_on_roster(self.player(5)))
        self.assertNotIn('player5', self.box_names_by_username(self.session))
        self.assertNotIn('player5', self.box_names_by_username(proposal))

    def test_completed_sessions_cannot_be_changed(self):
        self.start_next_session()
        with self.assertRaisesMessage(BoxLeagueRuleViolation, 'Completed sessions cannot be changed'):
            self.league.assign_to_box(self.player(3), self.silver)


class BoxLeagueResultTests(BoxLeagueTestBase):
    def setUp(self):
        super().setUp()
        self.session = self.start_next_session()
        self.box_match = self.box_match_between(self.session, self.player(1), self.player(2))

    def test_participant_records_a_tie(self):
        self.league.record_result(self.box_match, None, self.player(2).user)
        gold = self.summary_named(self.session, 'Gold')
        self.assertEqual([standing.points for standing in gold.standings[:2]], [1, 1])

    def test_outsider_cannot_record(self):
        with self.assertRaises(PermissionDenied):
            self.league.record_result(self.box_match, self.player(1), self.player(5).user)

    def test_result_can_only_be_recorded_once(self):
        self.league.record_result(self.box_match, self.player(1), self.player(1).user)
        with self.assertRaisesMessage(BoxLeagueRuleViolation, 'already has a result'):
            self.league.record_result(self.box_match, self.player(2), self.player(2).user)

    def test_winner_must_be_in_the_match(self):
        with self.assertRaisesMessage(BoxLeagueRuleViolation, 'must be one of the players'):
            self.league.record_result(self.box_match, self.player(3), self.organizer.user)

    def test_completed_session_rejects_results(self):
        self.start_next_session()
        with self.assertRaisesMessage(BoxLeagueRuleViolation, 'only be recorded while the session is active'):
            self.league.record_result(self.box_match, self.player(1), self.player(1).user)

    def test_organizer_changes_and_clears_results(self):
        self.league.record_result(self.box_match, self.player(1), self.player(1).user)
        self.league.change_result(self.box_match, self.player(2), self.organizer.user)
        self.box_match.match.refresh_from_db()
        self.assertEqual(self.box_match.match.result.winner, self.player(2))

        self.league.clear_result(self.box_match, self.organizer.user)
        self.box_match = BoxMatch.objects.get(pk=self.box_match.pk)
        self.assertFalse(self.box_match.match.has_result())
        self.league.record_result(self.box_match, self.player(1), self.player(1).user)

    def test_players_cannot_change_or_clear(self):
        self.league.record_result(self.box_match, self.player(1), self.player(1).user)
        with self.assertRaises(PermissionDenied):
            self.league.change_result(self.box_match, self.player(2), self.player(2).user)
        with self.assertRaises(PermissionDenied):
            self.league.clear_result(self.box_match, self.player(2).user)


@override_settings(STORAGES=SIMPLE_STORAGES)
class BoxLeagueViewTests(BoxLeagueTestBase):
    def league_url(self, name, *args):
        return reverse(name, args=[self.playgroup.slug, self.league.pk, *args])

    def message_texts(self, response):
        return [str(message) for message in get_messages(response.wsgi_request)]

    def test_disabled_feature_redirects_to_the_playgroup(self):
        PlaygroupFeature.objects.filter(playgroup=self.playgroup).update(is_enabled=False)
        self.client.force_login(self.organizer.user)
        playgroup_url = reverse('pmc-pg-detail', args=[self.playgroup.slug])
        self.assertRedirects(
            self.client.get(reverse('pmc-pg-box-leagues', args=[self.playgroup.slug])), playgroup_url)
        self.assertRedirects(self.client.get(self.league_url('pmc-pg-box-league-manage')), playgroup_url)
        response = self.client.get(playgroup_url)
        self.assertNotIn('Play', [str(link['name']) for link in response.context['nav_links']])
        self.assertRedirects(
            self.client.get(reverse('pmc-pg-play', args=[self.playgroup.slug])), playgroup_url)

    def test_nav_and_playgroup_page_show_box_leagues_when_enabled(self):
        self.client.force_login(self.player(1).user)
        response = self.client.get(reverse('pmc-pg-detail', args=[self.playgroup.slug]))
        self.assertIn('Play', [str(link['name']) for link in response.context['nav_links']])
        self.assertContains(response, 'Winter League')

    def test_play_page_lists_only_enabled_formats(self):
        self.client.force_login(self.player(1).user)
        response = self.client.get(reverse('pmc-pg-play', args=[self.playgroup.slug]))
        self.assertContains(response, 'Winter League')
        self.assertIsNone(response.context['ladders'])
        self.assertNotContains(response, 'Add Ladder')

    def test_play_link_is_active_on_box_league_pages(self):
        session = self.start_next_session()
        self.client.force_login(self.player(1).user)
        response = self.client.get(self.league_url('pmc-pg-box-league-session', session.number))
        active_names = [str(link['name']) for link in response.context['nav_links'] if link['is_active']]
        self.assertEqual(active_names, ['Play'])

    def test_manage_page_warns_about_unbalanced_movement(self):
        self.league.promotion_count = 2
        self.league.save()
        self.client.force_login(self.organizer.user)
        response = self.client.get(self.league_url('pmc-pg-box-league-manage'))
        self.assertContains(response, 'More players move up than down each session.')

    def test_resize_and_box_views(self):
        proposal = self.league.plan_next_session()
        self.client.force_login(self.organizer.user)
        self.client.post(self.league_url('pmc-pg-box-league-resize'), {'box_count': 2})
        self.assertEqual(len(proposal.get_box_summaries()), 2)

        self.client.post(self.league_url('pmc-pg-box-league-box-add', proposal.number), {'level': 3})
        empty_box = proposal.get_box_summaries()[-1].box
        self.client.post(self.league_url('pmc-pg-box-league-box-remove', proposal.number, empty_box.pk))
        self.assertEqual(len(proposal.get_box_summaries()), 2)

    def test_league_home_redirects_to_the_current_session(self):
        session = self.start_next_session()
        self.client.force_login(self.player(1).user)
        response = self.client.get(self.league_url('pmc-pg-box-league-detail'))
        self.assertRedirects(response, self.league_url('pmc-pg-box-league-session', session.number))

    def test_league_home_without_sessions_renders_an_empty_state(self):
        self.client.force_login(self.player(1).user)
        response = self.client.get(self.league_url('pmc-pg-box-league-detail'))
        self.assertContains(response, 'No sessions yet')

    def test_session_page_shows_your_box_and_session_links(self):
        first_session = self.start_next_session()
        second_session = self.start_next_session()
        self.client.force_login(self.player(5).user)
        response = self.client.get(self.league_url('pmc-pg-box-league-session', second_session.number))
        self.assertEqual(response.context['viewer_summary'].name, 'Silver')
        self.assertContains(response, self.league_url('pmc-pg-box-league-session', first_session.number))

    def test_confirming_from_the_proposal_page(self):
        self.start_next_session()
        proposal = self.league.plan_next_session()
        self.client.force_login(self.player(4).user)
        response = self.client.get(self.league_url('pmc-pg-box-league-session', proposal.number))
        self.assertContains(response, "Confirm I'm In")
        self.client.post(self.league_url('pmc-pg-box-league-confirm'))
        self.assertIn(self.player(4).pk, proposal.get_confirmed_member_ids())

    def test_record_result_view_for_participants_only(self):
        session = self.start_next_session()
        box_match = self.box_match_between(session, self.player(1), self.player(2))
        result_url = self.league_url('pmc-pg-box-league-match-result', box_match.pk)

        self.client.force_login(self.player(5).user)
        self.assertEqual(self.client.get(result_url).status_code, 403)

        self.client.force_login(self.player(2).user)
        self.client.post(result_url, {'outcome': 'tie'})
        box_match.match.refresh_from_db()
        self.assertTrue(box_match.match.result.is_tie())

        response = self.client.get(result_url)
        self.assertIn('This match already has a result. Ask an organizer to change it.',
                      self.message_texts(response))

    def test_organizer_changes_and_clears_a_result_through_views(self):
        session = self.start_next_session()
        box_match = self.box_match_between(session, self.player(1), self.player(2))
        self.league.record_result(box_match, self.player(1), self.player(1).user)
        self.client.force_login(self.organizer.user)
        result_url = self.league_url('pmc-pg-box-league-match-result', box_match.pk)

        response = self.client.get(result_url)
        self.assertEqual(response.context['form'].initial['outcome'], 'player_one')
        self.client.post(result_url, {'outcome': 'player_two'})
        box_match.match.refresh_from_db()
        self.assertEqual(box_match.match.result.winner, self.player(2))

        self.client.post(self.league_url('pmc-pg-box-league-match-clear', box_match.pk))
        self.assertFalse(Match.objects.get(pk=box_match.match_id).has_result())

    def test_create_league(self):
        self.client.force_login(self.organizer.user)
        response = self.client.post(reverse('pmc-pg-box-league-new', args=[self.playgroup.slug]), {
            'name': 'Spring League',
            'layout': 'pyramid',
            'target_box_size': 4,
            'promotion_count': 1,
            'relegation_count': 1,
            'session_length_months': 1,
        })
        league = BoxLeague.objects.get(name='Spring League')
        self.assertRedirects(response, reverse(
            'pmc-pg-box-league-manage', args=[self.playgroup.slug, league.pk]))
        self.assertEqual((league.layout, league.target_box_size), ('pyramid', 4))

    def test_create_league_requires_at_least_two_players_per_box(self):
        self.client.force_login(self.organizer.user)
        response = self.client.post(reverse('pmc-pg-box-league-new', args=[self.playgroup.slug]), {
            'name': 'Tiny League',
            'layout': 'linear',
            'target_box_size': 1,
            'promotion_count': 1,
            'relegation_count': 1,
            'session_length_months': 1,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoxLeague.objects.filter(name='Tiny League').exists())

    def test_edit_league_renames_tiers(self):
        self.client.force_login(self.organizer.user)
        response = self.client.post(self.league_url('pmc-pg-box-league-edit'), {
            'name': 'Winter League',
            'layout': 'linear',
            'target_box_size': 3,
            'promotion_count': 1,
            'relegation_count': 1,
            'session_length_months': 1,
            'tiers-TOTAL_FORMS': 4,
            'tiers-INITIAL_FORMS': 3,
            'tiers-MIN_NUM_FORMS': 0,
            'tiers-MAX_NUM_FORMS': 1000,
            'tiers-0-name': 'Champions',
            'tiers-1-name': 'Challengers',
            'tiers-2-name': 'Bronze',
            'tiers-2-DELETE': 'on',
            'tiers-3-name': '',
        })
        self.assertRedirects(response, self.league_url('pmc-pg-box-league-manage'))
        self.assertEqual(
            [(tier.level, tier.name) for tier in self.league.get_tiers()],
            [(1, 'Champions'), (2, 'Challengers')])

    def test_start_session_view_suggests_dates_and_starts(self):
        self.league.plan_next_session()
        self.client.force_login(self.organizer.user)
        start_url = self.league_url('pmc-pg-box-league-start')
        response = self.client.get(start_url)
        initial = response.context['form'].initial
        self.assertEqual(initial['ends_on'], self.league.suggested_end_date(initial['starts_on']))

        self.client.post(start_url, {'starts_on': '2026-10-01', 'ends_on': '2026-11-01'})
        self.assertTrue(self.league.get_active_session().is_active())

    def test_assign_view_moves_a_player(self):
        session = self.start_next_session()
        bronze = self.summary_named(session, 'Bronze').box
        self.client.force_login(self.organizer.user)
        self.client.post(self.league_url('pmc-pg-box-league-assign', session.number), {
            'member': self.player(1).pk,
            'box': bronze.pk,
        })
        self.assertEqual(self.box_names_by_username(session)['player1'], 'Bronze')

    def test_assign_view_adds_a_new_player_straight_into_a_box(self):
        session = self.start_next_session()
        newcomer = self.create_member('newcomer')
        bronze = self.summary_named(session, 'Bronze').box
        self.client.force_login(self.organizer.user)
        self.client.post(self.league_url('pmc-pg-box-league-assign', session.number), {
            'member': newcomer.pk,
            'box': bronze.pk,
        })
        self.assertTrue(self.league.is_on_roster(newcomer))
        self.assertEqual(self.box_names_by_username(session)['newcomer'], 'Bronze')

    def test_box_match_from_another_league_is_not_found(self):
        other_league = BoxLeague.objects.create(playgroup=self.playgroup, name='Other League')
        other_league.join(self.player(1))
        other_league.join(self.player(2))
        other_league.plan_next_session()
        other_session = other_league.start_session(date(2026, 10, 1), date(2026, 11, 1))
        other_box_match = BoxMatch.objects.get(box__session=other_session)
        self.client.force_login(self.player(1).user)
        response = self.client.get(
            self.league_url('pmc-pg-box-league-match-result', other_box_match.pk))
        self.assertEqual(response.status_code, 404)

    def test_staff_actions_are_forbidden_for_players(self):
        self.client.force_login(self.player(1).user)
        self.assertEqual(self.client.get(self.league_url('pmc-pg-box-league-manage')).status_code, 403)
        self.assertEqual(self.client.post(self.league_url('pmc-pg-box-league-plan')).status_code, 403)
        self.assertFalse(BoxLeagueSession.objects.exists())

    def test_join_and_leave_views(self):
        newcomer = self.create_member('newcomer')
        self.client.force_login(newcomer.user)
        self.client.post(self.league_url('pmc-pg-box-league-join'))
        self.assertTrue(self.league.is_on_roster(newcomer))
        response = self.client.post(self.league_url('pmc-pg-box-league-leave'), HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Redirect'], self.league_url('pmc-pg-box-league-detail'))
        self.assertFalse(self.league.is_on_roster(newcomer))

    def test_global_playgroups_have_no_box_leagues(self):
        global_playgroup = Playgroup.objects.create(name='Global', slug='global', is_global=True)
        self.enable_box_leagues_for(global_playgroup)
        self.client.force_login(self.player(1).user)
        response = self.client.get(reverse('pmc-pg-box-leagues', args=[global_playgroup.slug]))
        self.assertEqual(response.status_code, 404)

    def test_league_from_another_playgroup_is_not_found(self):
        other_playgroup = Playgroup.objects.create(name='Other', slug='other')
        self.enable_box_leagues_for(other_playgroup)
        other_member = self.create_member('other-member', playgroup=other_playgroup)
        self.client.force_login(other_member.user)
        response = self.client.get(
            reverse('pmc-pg-box-league-manage', args=[other_playgroup.slug, self.league.pk]))
        self.assertIn(response.status_code, (403, 404))
        response = self.client.get(
            reverse('pmc-pg-box-league-detail', args=[other_playgroup.slug, self.league.pk]))
        self.assertEqual(response.status_code, 404)
