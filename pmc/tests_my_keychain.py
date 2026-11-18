from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import my_keychain
from .models import (
    BoxLeague, BoxMatch, Event, EventFormat, EventResult, Feature, Ladder, Leaderboard, LeaderboardSeason,
    LeaderboardSeasonPeriod, PlayerRank, Playgroup, PlaygroupEvent, PlaygroupFeature, PlaygroupLeaderboard,
    PlaygroupMember, RankingPoints,
)


SIMPLE_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


class MyKeychainTestBase(TestCase):
    def setUp(self):
        self.playgroup = Playgroup.objects.create(name='The Lounge', slug='the-lounge')
        self.viewer = self.create_member('viewer')
        self.opponent = self.create_member('opponent')

    def create_member(self, username, playgroup=None):
        user = User.objects.filter(username=username).first() or User.objects.create_user(username=username)
        return PlaygroupMember.objects.create(playgroup=playgroup or self.playgroup, user=user)

    def set_feature(self, key, playgroup=None, is_enabled=True):
        PlaygroupFeature.objects.update_or_create(
            playgroup=playgroup or self.playgroup,
            feature=Feature.objects.get(key=key),
            defaults={'is_enabled': is_enabled},
        )

    def create_ladder_challenge(self, challenger, defender, name='Summer Ladder'):
        ladder = Ladder.objects.create(playgroup=defender.playgroup, name=name)
        ladder.add_member(defender)
        ladder.add_member(challenger)
        return ladder.issue_challenge(challenger, defender)

    def create_active_box_league(self, members, ends_on):
        league = BoxLeague.objects.create(playgroup=self.playgroup, name='Winter League', target_box_size=3)
        for member in members:
            league.join(member)
        league.plan_next_session()
        league.start_session(date.today(), ends_on)
        return league

    def create_event(self, name, start_date, playgroup=None, **fields):
        event = Event.objects.create(name=name, start_date=start_date, **fields)
        PlaygroupEvent.objects.create(playgroup=playgroup or self.playgroup, event=event)
        return event

    def up_next(self):
        return my_keychain.build_up_next(self.viewer.user)


class UpNextTests(MyKeychainTestBase):
    def test_nothing_pending_gives_no_up_next(self):
        self.assertIsNone(self.up_next())

    def test_received_ladder_challenge_is_due(self):
        self.set_feature(Feature.Keys.LADDERS)
        challenge = self.create_ladder_challenge(self.opponent, self.viewer)
        up_next = self.up_next()
        self.assertTrue(up_next.is_due)
        self.assertEqual(up_next.headline.title, 'opponent challenged you')
        self.assertEqual(up_next.headline.url, reverse('pmc-pg-ladder-challenge-result', kwargs={
            'slug': 'the-lounge', 'ladder_id': challenge.ladder_id, 'challenge_id': challenge.pk}))

    def test_issued_ladder_challenge_names_the_defender(self):
        self.set_feature(Feature.Keys.LADDERS)
        self.create_ladder_challenge(self.viewer, self.opponent)
        self.assertEqual(self.up_next().headline.title, 'You challenged opponent')

    def test_ladder_challenge_is_hidden_when_ladders_are_disabled(self):
        self.set_feature(Feature.Keys.LADDERS)
        self.create_ladder_challenge(self.opponent, self.viewer)
        self.set_feature(Feature.Keys.LADDERS, is_enabled=False)
        self.assertIsNone(self.up_next())

    def test_overdue_ladder_challenge_is_not_shown(self):
        self.set_feature(Feature.Keys.LADDERS)
        challenge = self.create_ladder_challenge(self.opponent, self.viewer)
        challenge.respond_by = timezone.now() - timedelta(days=1)
        challenge.save()
        self.assertIsNone(self.up_next())

    def test_challenges_between_other_players_are_not_shown(self):
        self.set_feature(Feature.Keys.LADDERS)
        self.create_ladder_challenge(self.opponent, self.create_member('bystander'))
        self.assertIsNone(self.up_next())

    def test_unplayed_box_match_is_due(self):
        self.set_feature(Feature.Keys.BOX_LEAGUES)
        league = self.create_active_box_league([self.viewer, self.opponent], date.today() + timedelta(days=20))
        box_match = BoxMatch.objects.get(box__session__league=league)
        up_next = self.up_next()
        self.assertTrue(up_next.is_due)
        self.assertEqual(up_next.headline.title, 'Box match vs opponent')
        self.assertEqual(up_next.headline.url, reverse('pmc-pg-box-league-match-result', kwargs={
            'slug': 'the-lounge', 'league_id': league.pk, 'box_match_id': box_match.pk}))

    def test_played_box_match_is_not_shown(self):
        self.set_feature(Feature.Keys.BOX_LEAGUES)
        league = self.create_active_box_league([self.viewer, self.opponent], date.today() + timedelta(days=20))
        league.record_result(BoxMatch.objects.get(box__session__league=league), self.viewer, self.viewer.user)
        self.assertIsNone(self.up_next())

    def test_unconfirmed_box_proposal_asks_for_review(self):
        self.set_feature(Feature.Keys.BOX_LEAGUES)
        league = BoxLeague.objects.create(playgroup=self.playgroup, name='Winter League', target_box_size=3)
        league.join(self.viewer)
        league.join(self.opponent)
        proposal = league.plan_next_session()
        up_next = self.up_next()
        self.assertTrue(up_next.is_due)
        self.assertEqual(up_next.headline.action_label, 'Review')
        self.assertEqual(up_next.headline.url, reverse('pmc-pg-box-league-session', kwargs={
            'slug': 'the-lounge', 'league_id': league.pk, 'number': proposal.number}))
        league.confirm(self.viewer)
        self.assertIsNone(self.up_next())

    def test_soonest_deadline_is_the_headline(self):
        self.set_feature(Feature.Keys.LADDERS)
        self.set_feature(Feature.Keys.BOX_LEAGUES)
        self.create_ladder_challenge(self.opponent, self.viewer)
        self.create_active_box_league([self.viewer, self.opponent], date.today() + timedelta(days=2))
        up_next = self.up_next()
        self.assertEqual(up_next.headline.title, 'Box match vs opponent')
        self.assertEqual([item.title for item in up_next.additional_items], ['opponent challenged you'])

    def test_registered_events_follow_owed_items(self):
        self.set_feature(Feature.Keys.LADDERS)
        self.create_ladder_challenge(self.opponent, self.viewer)
        event = self.create_event('Friday Night Archon', date.today() + timedelta(days=3))
        EventResult.objects.create(event=event, user=self.viewer.user)
        up_next = self.up_next()
        self.assertEqual(up_next.headline.title, 'opponent challenged you')
        self.assertEqual([item.title for item in up_next.additional_items], ['Friday Night Archon'])
        self.assertTrue(up_next.additional_items[0].is_registered)

    def test_registered_event_is_up_next_when_nothing_is_owed(self):
        event = self.create_event('Friday Night Archon', date.today() + timedelta(days=3))
        EventResult.objects.create(event=event, user=self.viewer.user)
        up_next = self.up_next()
        self.assertFalse(up_next.is_due)
        self.assertEqual(up_next.headline.title, 'Friday Night Archon')
        self.assertEqual(up_next.headline.url, reverse(
            'pmc-pg-event-detail', kwargs={'slug': 'the-lounge', 'pk': event.pk}))

    def test_open_registration_is_suggested(self):
        self.create_event('Later Event', date.today() + timedelta(days=9), is_accepting_registrations=True)
        self.create_event('Store Championship', date.today() + timedelta(days=5), is_accepting_registrations=True)
        up_next = self.up_next()
        self.assertFalse(up_next.is_due)
        self.assertFalse(up_next.headline.is_registered)
        self.assertEqual(up_next.headline.title, 'Store Championship')
        self.assertEqual(up_next.additional_items, [])

    def test_open_registration_in_another_playgroup_is_not_suggested(self):
        other_playgroup = Playgroup.objects.create(name='Elsewhere', slug='elsewhere')
        self.create_event(
            'Away Day', date.today() + timedelta(days=5), playgroup=other_playgroup, is_accepting_registrations=True)
        self.assertIsNone(self.up_next())

    def test_closed_or_past_events_are_not_suggested(self):
        self.create_event('Closed', date.today() + timedelta(days=5))
        self.create_event('Past', date.today() - timedelta(days=5), is_accepting_registrations=True)
        self.assertIsNone(self.up_next())


class PlayerStatsTests(MyKeychainTestBase):
    def stats(self):
        return my_keychain.build_player_stats(
            self.viewer.user, self.viewer.user.pmc_profile.get_events(exclude_upcoming=True))

    def test_stats_without_results(self):
        stats = self.stats()
        self.assertEqual((stats.events_attended, stats.events_won, stats.match_wins), (0, 0, 0))
        self.assertIsNone(stats.win_rate)
        self.assertIsNone(stats.best_finish)
        self.assertIsNone(stats.playing_since)
        self.assertEqual((stats.podium_finishes, stats.awards_earned), (0, 0))
        self.assertIsNone(stats.match_record)
        self.assertIsNone(stats.favorite_format)

    def test_stats_from_results(self):
        archon = EventFormat.objects.create(name='Archon')
        sealed = EventFormat.objects.create(name='Sealed')
        first_event = self.create_event('First', date(2025, 2, 10), format=archon)
        second_event = self.create_event('Second', date(2025, 6, 10), format=archon)
        third_event = self.create_event('Third', date(2025, 7, 10), format=sealed)
        EventResult.objects.create(
            event=first_event, user=self.viewer.user, finishing_position=3, num_wins=1, num_losses=2)
        EventResult.objects.create(
            event=third_event, user=self.viewer.user, finishing_position=7, num_wins=0, num_losses=0)
        best = EventResult.objects.create(
            event=second_event, user=self.viewer.user, finishing_position=1, num_wins=3, num_losses=0)
        stats = self.stats()
        self.assertEqual((stats.events_attended, stats.events_won, stats.match_wins), (3, 1, 4))
        self.assertEqual(stats.podium_finishes, 2)
        self.assertEqual(stats.match_record, '4\u20132')
        self.assertEqual(stats.favorite_format, 'Archon')
        self.assertEqual(stats.win_rate, 67)
        self.assertEqual(stats.best_finish, best)
        self.assertEqual(stats.playing_since, date(2025, 2, 10))


class PlaygroupRowTests(MyKeychainTestBase):
    def setUp(self):
        super().setUp()
        self.leaderboard = Leaderboard.objects.create(
            name='Monthly', period_frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH)
        self.season = LeaderboardSeason.objects.create(name='Test Season')

    def rank_viewer(self, rank, start_date=None):
        period = LeaderboardSeasonPeriod.objects.create(
            name='Period', start_date=start_date or date.today().replace(day=1), season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH)
        PlayerRank.objects.create(
            user=self.viewer.user, playgroup=self.playgroup, rank=rank, leaderboard=self.leaderboard, period=period)

    def rows(self):
        return my_keychain.build_playgroup_rows(self.viewer.user)

    def test_rank_this_month_is_shown(self):
        self.rank_viewer(3)
        self.assertEqual(self.rows()[0].rank_this_month, 3)

    def test_rank_from_an_earlier_month_is_not_shown(self):
        self.rank_viewer(3, start_date=date(2020, 1, 1))
        self.assertIsNone(self.rows()[0].rank_this_month)

    def test_rank_on_a_hidden_leaderboard_is_not_shown(self):
        self.rank_viewer(3)
        PlaygroupLeaderboard.objects.create(
            playgroup=self.playgroup, leaderboard=self.leaderboard, is_leaderboard_hidden=True)
        self.assertIsNone(self.rows()[0].rank_this_month)

    def test_global_playgroups_follow_memberships(self):
        global_playgroup = Playgroup.objects.create(name='Global', slug='global', is_global=True)
        self.create_event('Next Up', date.today() + timedelta(days=4))
        rows = self.rows()
        self.assertEqual([row.playgroup for row in rows], [self.playgroup, global_playgroup])
        self.assertEqual([row.is_global for row in rows], [False, True])
        self.assertEqual(rows[0].playgroup.next_event_date, date.today() + timedelta(days=4))


@override_settings(STORAGES=SIMPLE_STORAGES)
class MyKeychainPageTests(MyKeychainTestBase):
    def get_page(self, **query):
        self.client.force_login(self.viewer.user)
        return self.client.get(reverse('pmc-my-keychain'), query)

    def test_page_renders_for_a_new_player(self):
        new_user = User.objects.create_user(username='newcomer')
        self.client.force_login(new_user)
        response = self.client.get(reverse('pmc-my-keychain'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No results yet.')
        self.assertContains(response, 'No playgroups yet.')
        self.assertNotContains(response, 'Last time out')

    def test_due_item_shows_your_move(self):
        self.set_feature(Feature.Keys.LADDERS)
        self.create_ladder_challenge(self.opponent, self.viewer)
        response = self.get_page()
        self.assertContains(response, 'Your move')
        self.assertContains(response, 'opponent challenged you')
        self.assertContains(response, 'Record Result')

    def test_recap_replaces_up_next_when_nothing_is_pending(self):
        event = self.create_event('Friday Night Archon', date.today() - timedelta(days=7), player_count=16)
        result = EventResult.objects.create(
            event=event, user=self.viewer.user, finishing_position=2, num_wins=3, num_losses=1)
        RankingPoints.objects.create(result=result, points=32)
        response = self.get_page()
        self.assertContains(response, 'Last time out')
        self.assertContains(response, '2nd of 16')
        self.assertContains(response, '+32')
        self.assertNotContains(response, 'Your move')
        self.assertEqual([activity.result for activity in response.context['recent_activity']], [result])

    def test_recent_activity_is_limited_to_the_latest_results(self):
        for days_ago in range(2, 7):
            event = self.create_event(f'Event {days_ago}', date.today() - timedelta(days=days_ago))
            EventResult.objects.create(event=event, user=self.viewer.user, finishing_position=1)
        response = self.get_page()
        self.assertEqual(
            [activity.result.event.name for activity in response.context['recent_activity']],
            ['Event 2', 'Event 3', 'Event 4'])

    def test_stats_side_replaces_the_playercard(self):
        self.assertContains(self.get_page(), 'class="playercard')
        response = self.get_page(side='stats')
        self.assertNotContains(response, 'class="playercard')
        self.assertContains(response, 'Win Rate')

    def test_playgroups_are_listed_without_membership_details(self):
        response = self.get_page()
        self.assertContains(response, reverse('pmc-pg-detail', kwargs={'slug': 'the-lounge'}))
        self.assertNotContains(response, 'Member Since')
        self.assertNotContains(response, 'Nickname')
