from django.test import TestCase
from django.contrib.auth.models import User
from datetime import date, timedelta
from .models import (
    Event, EventResult, RankingPoints, Leaderboard, LeaderboardSeason,
    LeaderboardSeasonPeriod, PlayerRank, Playgroup, PlaygroupEvent,
    RankingPointsMapVersion, RankingPointsMap, RankingPointsService,
    EventFormat, AwardBase, Achievement, Trophy, AwardAssignmentService,
    EventResultDeck, AwardCredit, LevelBreakpoint, AchievementTier
)
from decks.models import House, Set, Deck
import uuid


class TopNPerMonthRankingTest(TestCase):
    """
    Tests for the top_n_per_month ranking calculation.

    This test verifies that rankings only consider the top N results
    within each calendar month of the ranking period, rather than the
    top N results across the entire period.
    """

    def setUp(self):
        self.create_ranking_points_map()
        self.create_users()
        self.create_playgroup()
        self.create_leaderboard()

    def create_ranking_points_map(self):
        """Create a basic ranking points map version and entries."""
        self.version = RankingPointsMapVersion.objects.create(
            name='Test Version',
            effective_on=date(2025, 1, 1)
        )

        for max_players in [3, 4, 8, 16, 32, 64]:
            RankingPointsMap.objects.create(
                max_players=max_players,
                finishing_position=1,
                points=100,
                version=self.version
            )
            RankingPointsMap.objects.create(
                max_players=max_players,
                finishing_position=2,
                points=80,
                version=self.version
            )
            RankingPointsMap.objects.create(
                max_players=max_players,
                finishing_position=3,
                points=60,
                version=self.version
            )

    def create_users(self):
        """Create test users."""
        self.user_a = User.objects.create_user(
            username='user_a',
            email='a@test.com'
        )
        self.user_b = User.objects.create_user(
            username='user_b',
            email='b@test.com'
        )

    def create_playgroup(self):
        """Create a test playgroup."""
        self.playgroup = Playgroup.objects.create(
            name='Test Playgroup',
            slug='test-playgroup'
        )

    def create_leaderboard(self):
        """Create a test leaderboard with a month-based frequency."""
        self.leaderboard = Leaderboard.objects.create(
            name='Monthly Rankings',
            sort_order=1,
            period_frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH
        )

    def create_event_and_result(self, user, finishing_position, event_date, points_value):
        """Helper to create an event and result for a user."""
        event = Event.objects.create(
            name=f'Event on {event_date}',
            start_date=event_date,
            player_count=3
        )
        PlaygroupEvent.objects.create(
            playgroup=self.playgroup,
            event=event
        )

        result = EventResult.objects.create(
            user=user,
            event=event,
            finishing_position=finishing_position,
            num_wins=0,
            num_losses=0
        )

        RankingPoints.objects.create(
            result=result,
            points=points_value
        )

        return event, result

    def test_top_n_per_month_limits_results_per_calendar_month(self):
        """
        Test that with top_n_per_month=2, only the top 2 results
        in each calendar month are counted.

        Scenario:
        - Period spans January and February 2025
        - User A has 4 results in January (100, 100, 80, 80 points)
        - User A has 0 results in February
        - With top_n_per_month=2:
          * January: 100 + 100 = 200 points (from top 2)
          * February: 0 points
          * Total: 200 points, Average: 200/2 = 100
        - With old top_n=2 behavior: 100 + 100 = 200 (from top 2 globally)
        """
        # Create events in January 2025
        jan_1 = self.create_event_and_result(
            self.user_a, 1, date(2025, 1, 5), 100
        )
        jan_2 = self.create_event_and_result(
            self.user_a, 1, date(2025, 1, 12), 100
        )
        jan_3 = self.create_event_and_result(
            self.user_a, 2, date(2025, 1, 19), 80
        )
        jan_4 = self.create_event_and_result(
            self.user_a, 2, date(2025, 1, 26), 80
        )

        # Get the ranking period (January 2025)
        period = self.leaderboard.get_period_for_date(date(2025, 1, 15))

        # Calculate rankings with top_n_per_month=2
        rankings = RankingPointsService.assign_points_for_leaderboard(
            self.leaderboard,
            period,
            top_n_per_month=2
        )

        # Verify user A's ranking
        user_a_rank = PlayerRank.objects.get(
            user=self.user_a,
            leaderboard=self.leaderboard,
            period=period,
            playgroup=None
        )

        # Should have only top 2 results (100 + 100 = 200)
        self.assertEqual(user_a_rank.total_points, 200)
        self.assertEqual(user_a_rank.num_results, 2)
        self.assertEqual(user_a_rank.average_points, 100)

    def test_top_n_per_month_across_multiple_months(self):
        """
        Test that top_n_per_month properly limits results when
        a period spans multiple months.

        Scenario:
        - Period spans January 2025
        - User A: 3 results in January (100, 80, 60 points)
        - With top_n_per_month=2:
          * January: top 2 = 100 + 80 = 180
          * Total: 180 points from 2 results
          * Average: 180/2 = 90
        """
        # January results
        self.create_event_and_result(self.user_a, 1, date(2025, 1, 5), 100)
        self.create_event_and_result(self.user_a, 2, date(2025, 1, 12), 80)
        self.create_event_and_result(self.user_a, 3, date(2025, 1, 19), 60)

        # Get January period
        period = self.leaderboard.get_period_for_date(date(2025, 1, 15))
        # Create next period so ranking calculation knows when January ends
        LeaderboardSeasonPeriod.objects.get_or_create(
            name='February 2025',
            start_date=date(2025, 2, 1),
            season=period.season,
            frequency=self.leaderboard.period_frequency
        )

        # Calculate rankings
        rankings = RankingPointsService.assign_points_for_leaderboard(
            self.leaderboard,
            period,
            top_n_per_month=2
        )

        # Verify user A's ranking for January period
        user_a_rank = PlayerRank.objects.get(
            user=self.user_a,
            leaderboard=self.leaderboard,
            period=period,
            playgroup=None
        )

        # Should have 2 results from January only (100 + 80 = 180)
        self.assertEqual(user_a_rank.total_points, 180)
        self.assertEqual(user_a_rank.num_results, 2)
        self.assertEqual(user_a_rank.average_points, 90)

    def test_top_n_per_month_affects_ranking_order(self):
        """
        Test that rankings change when using top_n_per_month vs old top_n.

        Scenario:
        - User A: 4 results in January (100, 100, 80, 80 points) = 440 total
        - User B: 2 results in January (95, 95 points) = 190 total
        - With old top_n=2: User A (200), User B (190) -> A ranks first
        - With top_n_per_month=2: User A (200), User B (190) -> A ranks first
        - But if we add:
        - User A: 2 results in January (100, 100, 80, 80 points)
        - User B: 4 results in January (95, 95, 90, 90 points)
        - With old top_n=2: User A (200), User B (190) -> A ranks first
        - With top_n_per_month=2: User A (200), User B (190) -> A ranks first

        This test verifies the basic ranking order with per-month limiting.
        """
        # User A: 4 results in January
        self.create_event_and_result(self.user_a, 1, date(2025, 1, 5), 100)
        self.create_event_and_result(self.user_a, 1, date(2025, 1, 12), 100)
        self.create_event_and_result(self.user_a, 2, date(2025, 1, 19), 80)
        self.create_event_and_result(self.user_a, 2, date(2025, 1, 26), 80)

        # User B: 2 results in January (both high-scoring)
        self.create_event_and_result(self.user_b, 1, date(2025, 1, 5), 95)
        self.create_event_and_result(self.user_b, 1, date(2025, 1, 12), 95)

        # Get January period
        period = self.leaderboard.get_period_for_date(date(2025, 1, 15))

        # Calculate rankings
        rankings = RankingPointsService.assign_points_for_leaderboard(
            self.leaderboard,
            period,
            top_n_per_month=2
        )

        # Verify rankings
        user_a_rank = PlayerRank.objects.get(
            user=self.user_a,
            leaderboard=self.leaderboard,
            period=period,
            playgroup=None
        )
        user_b_rank = PlayerRank.objects.get(
            user=self.user_b,
            leaderboard=self.leaderboard,
            period=period,
            playgroup=None
        )

        # User A should have 200 points, User B should have 190
        self.assertEqual(user_a_rank.total_points, 200)
        self.assertEqual(user_b_rank.total_points, 190)

        # User A should rank higher
        self.assertEqual(user_a_rank.rank, 1)
        self.assertEqual(user_b_rank.rank, 2)

    def test_top_n_per_month_only_applies_to_global_rankings(self):
        """
        Test that top_n_per_month only limits global rankings, not playgroup rankings.

        Scenario:
        - User A has 4 results in January (100, 100, 80, 80 points)
        - With top_n_per_month=2:
          * Global: 100 + 100 = 200 points (limited to top 2)
          * Playgroup: 100 + 100 + 80 + 80 = 360 points (all results)
        """
        self.create_event_and_result(self.user_a, 1, date(2025, 1, 5), 100)
        self.create_event_and_result(self.user_a, 1, date(2025, 1, 12), 100)
        self.create_event_and_result(self.user_a, 2, date(2025, 1, 19), 80)
        self.create_event_and_result(self.user_a, 2, date(2025, 1, 26), 80)

        period = self.leaderboard.get_period_for_date(date(2025, 1, 15))

        RankingPointsService.assign_points_for_leaderboard(
            self.leaderboard,
            period,
            top_n_per_month=2
        )

        global_rank = PlayerRank.objects.get(
            user=self.user_a,
            leaderboard=self.leaderboard,
            period=period,
            playgroup=None
        )
        self.assertEqual(global_rank.total_points, 200)
        self.assertEqual(global_rank.num_results, 2)

        playgroup_rank = PlayerRank.objects.get(
            user=self.user_a,
            leaderboard=self.leaderboard,
            period=period,
            playgroup=self.playgroup
        )
        self.assertEqual(playgroup_rank.total_points, 360)
        self.assertEqual(playgroup_rank.num_results, 4)


class DummyAward:
    """Helper class to test criteria without needing actual Award objects."""
    def __init__(self, criteria, mode=AwardBase.ModeOptions.ANY, house=None):
        self.criteria = criteria
        self.mode = mode
        self.house = house


class AwardCriteriaTestBase(TestCase):
    """Base class with common setup for award criteria tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com'
        )
        self.playgroup = Playgroup.objects.create(
            name='Test Playgroup',
            slug='test-playgroup'
        )
        self.premier_playgroup = Playgroup.objects.create(
            name='Premier Tournaments',
            slug='premier-tournaments'
        )

    def create_event(self, start_date, player_count=8, is_casual=False,
                     is_digital=False, format_name=None, playgroup=None,
                     is_excluded_from_global_rankings=False):
        """Helper to create an event."""
        event = Event.objects.create(
            name=f'Event on {start_date}',
            start_date=start_date,
            player_count=player_count,
            is_casual=is_casual,
            is_digital=is_digital,
            is_excluded_from_global_rankings=is_excluded_from_global_rankings
        )

        if format_name:
            event_format, _ = EventFormat.objects.get_or_create(name=format_name)
            event.format = event_format
            event.save()

        if playgroup:
            PlaygroupEvent.objects.create(playgroup=playgroup, event=event)

        return event

    def create_result(self, event, user=None, finishing_position=1,
                      num_wins=3, num_losses=2):
        """Helper to create an event result."""
        if user is None:
            user = self.user
        return EventResult.objects.create(
            event=event,
            user=user,
            finishing_position=finishing_position,
            num_wins=num_wins,
            num_losses=num_losses
        )

    def get_criteria_value(self, criteria_type, mode=AwardBase.ModeOptions.ANY, house=None):
        """Helper to get criteria value for the test user."""
        award = DummyAward(criteria_type, mode, house)
        return AwardAssignmentService.get_user_criteria_value(self.user, award)


class BasicMatchAndEventCountingTests(AwardCriteriaTestBase):
    """Tests for criteria 0-10: basic match and event counting."""

    def test_event_matches_counts_all_matches(self):
        """Criteria 0: event_matches should count wins + losses."""
        event = self.create_event(date(2025, 1, 1))
        self.create_result(event, num_wins=3, num_losses=2)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.event_matches)
        self.assertEqual(value, 5)

    def test_event_matches_multiple_events(self):
        """Criteria 0: Should sum matches across multiple events."""
        event1 = self.create_event(date(2025, 1, 1))
        self.create_result(event1, num_wins=3, num_losses=2)

        event2 = self.create_event(date(2025, 1, 8))
        self.create_result(event2, num_wins=4, num_losses=1)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.event_matches)
        self.assertEqual(value, 10)

    def test_sealed_event_matches_only_counts_sealed_format(self):
        """Criteria 1: sealed_event_matches should only count Sealed format."""
        sealed_event = self.create_event(date(2025, 1, 1), format_name='Sealed')
        self.create_result(sealed_event, num_wins=3, num_losses=2)

        archon_event = self.create_event(date(2025, 1, 8), format_name='Archon')
        self.create_result(archon_event, num_wins=4, num_losses=1)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.sealed_event_matches)
        self.assertEqual(value, 5)

    def test_tournament_match_wins_excludes_casual_events(self):
        """Criteria 5: tournament_match_wins should exclude casual events."""
        tournament = self.create_event(date(2025, 1, 1), is_casual=False)
        self.create_result(tournament, num_wins=5, num_losses=2)

        casual = self.create_event(date(2025, 1, 8), is_casual=True)
        self.create_result(casual, num_wins=3, num_losses=0)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.tournament_match_wins)
        self.assertEqual(value, 5)

    def test_events_counts_all_participations(self):
        """Criteria 10: events should count all event participations."""
        for i in range(5):
            event = self.create_event(date(2025, 1, i + 1))
            self.create_result(event)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.events)
        self.assertEqual(value, 5)


class PlacementCriteriaTests(AwardCriteriaTestBase):
    """Tests for criteria 11-16: tournament placement awards."""

    def test_win_tournament_3_to_5_players(self):
        """Criteria 11: Should count 1st place in 3-5 player tournaments."""
        event_3 = self.create_event(date(2025, 1, 1), player_count=3)
        self.create_result(event_3, finishing_position=1)

        event_5 = self.create_event(date(2025, 1, 2), player_count=5)
        self.create_result(event_5, finishing_position=1)

        event_6 = self.create_event(date(2025, 1, 3), player_count=6)
        self.create_result(event_6, finishing_position=1)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.win_a_tournament_3_to_5)
        self.assertEqual(value, 2)

    def test_win_tournament_excludes_global_rankings(self):
        """Criteria 11 & 12: Should exclude tournaments in global rankings."""
        global_event = self.create_event(
            date(2025, 1, 1),
            player_count=4,
            is_excluded_from_global_rankings=False
        )
        self.create_result(global_event, finishing_position=1)

        local_event = self.create_event(
            date(2025, 1, 2),
            player_count=4,
            is_excluded_from_global_rankings=True
        )
        self.create_result(local_event, finishing_position=1)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.win_a_tournament_3_to_5)
        self.assertEqual(value, 1)

    def test_win_tournament_6_plus_players(self):
        """Criteria 12: Should count 1st place in 6+ player tournaments."""
        event_6 = self.create_event(date(2025, 1, 1), player_count=6)
        self.create_result(event_6, finishing_position=1)

        event_20 = self.create_event(date(2025, 1, 2), player_count=20)
        self.create_result(event_20, finishing_position=1)

        event_5 = self.create_event(date(2025, 1, 3), player_count=5)
        self.create_result(event_5, finishing_position=1)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.win_a_tournament_6_plus)
        self.assertEqual(value, 2)

    def test_second_place_6_plus_players(self):
        """Criteria 13: Should count 2nd place in 6+ player tournaments."""
        event_6 = self.create_event(date(2025, 1, 1), player_count=6)
        self.create_result(event_6, finishing_position=2)

        event_5 = self.create_event(date(2025, 1, 2), player_count=5)
        self.create_result(event_5, finishing_position=2)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.second_place_a_tournament_6_plus)
        self.assertEqual(value, 1)

    def test_third_place_6_to_10_players(self):
        """Criteria 14: Should count 3rd place in 6-10 player tournaments."""
        event_6 = self.create_event(date(2025, 1, 1), player_count=6)
        self.create_result(event_6, finishing_position=3)

        event_10 = self.create_event(date(2025, 1, 2), player_count=10)
        self.create_result(event_10, finishing_position=3)

        event_11 = self.create_event(date(2025, 1, 3), player_count=11)
        self.create_result(event_11, finishing_position=3)

        event_5 = self.create_event(date(2025, 1, 4), player_count=5)
        self.create_result(event_5, finishing_position=3)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.third_place_a_tournament_6_plus)
        self.assertEqual(value, 2)

    def test_top_four_11_plus_players(self):
        """Criteria 15: Should count 3rd-4th place in 11+ player tournaments."""
        event_11 = self.create_event(date(2025, 1, 1), player_count=11)
        self.create_result(event_11, finishing_position=3)

        event_20 = self.create_event(date(2025, 1, 2), player_count=20)
        self.create_result(event_20, finishing_position=4)

        event_10 = self.create_event(date(2025, 1, 3), player_count=10)
        self.create_result(event_10, finishing_position=3)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.top_four_a_tournament_11_plus)
        self.assertEqual(value, 2)

    def test_top_eight_11_plus_players(self):
        """Criteria 16: Should count 5th-8th place in 11+ player tournaments."""
        event_11 = self.create_event(date(2025, 1, 1), player_count=11)
        self.create_result(event_11, finishing_position=5)

        event_20 = self.create_event(date(2025, 1, 2), player_count=20)
        self.create_result(event_20, finishing_position=8)

        event_same = self.create_event(date(2025, 1, 3), player_count=15)
        self.create_result(event_same, finishing_position=4)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.top_eight_a_tournament_11_plus)
        self.assertEqual(value, 2)

    def test_placement_criteria_non_overlapping(self):
        """Verify placement criteria don't overlap for same tournament."""
        event = self.create_event(date(2025, 1, 1), player_count=15)
        self.create_result(event, finishing_position=3)

        top_four = self.get_criteria_value(AwardBase.CriteriaTypeOptions.top_four_a_tournament_11_plus)
        top_eight = self.get_criteria_value(AwardBase.CriteriaTypeOptions.top_eight_a_tournament_11_plus)
        third_place = self.get_criteria_value(AwardBase.CriteriaTypeOptions.third_place_a_tournament_6_plus)

        self.assertEqual(top_four, 1)
        self.assertEqual(top_eight, 0)
        self.assertEqual(third_place, 0)


class ModeCriteriaTests(AwardCriteriaTestBase):
    """Tests for mode filtering (IN_PERSON, ONLINE, ANY)."""

    def test_in_person_mode_excludes_digital_events(self):
        """IN_PERSON mode should exclude digital events."""
        in_person = self.create_event(date(2025, 1, 1), is_digital=False)
        self.create_result(in_person, num_wins=3, num_losses=2)

        digital = self.create_event(date(2025, 1, 2), is_digital=True)
        self.create_result(digital, num_wins=4, num_losses=1)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.event_matches,
            mode=AwardBase.ModeOptions.IN_PERSON
        )
        self.assertEqual(value, 5)

    def test_online_mode_excludes_in_person_events(self):
        """ONLINE mode should exclude in-person events."""
        in_person = self.create_event(date(2025, 1, 1), is_digital=False)
        self.create_result(in_person, num_wins=3, num_losses=2)

        digital = self.create_event(date(2025, 1, 2), is_digital=True)
        self.create_result(digital, num_wins=4, num_losses=1)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.event_matches,
            mode=AwardBase.ModeOptions.ONLINE
        )
        self.assertEqual(value, 5)

    def test_any_mode_includes_all_events(self):
        """ANY mode should include both digital and in-person events."""
        in_person = self.create_event(date(2025, 1, 1), is_digital=False)
        self.create_result(in_person, num_wins=3, num_losses=2)

        digital = self.create_event(date(2025, 1, 2), is_digital=True)
        self.create_result(digital, num_wins=4, num_losses=1)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.event_matches,
            mode=AwardBase.ModeOptions.ANY
        )
        self.assertEqual(value, 10)


class LevelCriteriaTests(AwardCriteriaTestBase):
    """Tests for criteria 20: level."""

    def test_level_criteria_returns_user_level(self):
        """Criteria 20: Should return user's current level."""
        LevelBreakpoint.objects.create(level=1, required_xp=0)
        LevelBreakpoint.objects.create(level=2, required_xp=100)
        LevelBreakpoint.objects.create(level=3, required_xp=500)

        event = self.create_event(date(2025, 1, 1))
        self.create_result(event, num_wins=10, num_losses=0)

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.level)
        self.assertGreaterEqual(value, 1)


class CalendarMonthCriteriaTests(AwardCriteriaTestBase):
    """Tests for criteria 21: events_at_group_in_calendar_month."""

    def test_counts_months_with_4_plus_events_at_same_playgroup(self):
        """Should count months with 4+ events at a single playgroup."""
        for i in range(4):
            event = self.create_event(
                date(2025, 1, i + 1),
                playgroup=self.playgroup
            )
            self.create_result(event)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.events_at_group_in_calendar_month
        )
        self.assertEqual(value, 1)

    def test_does_not_count_months_with_less_than_4_events(self):
        """Should not count months with fewer than 4 events."""
        for i in range(3):
            event = self.create_event(
                date(2025, 1, i + 1),
                playgroup=self.playgroup
            )
            self.create_result(event)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.events_at_group_in_calendar_month
        )
        self.assertEqual(value, 0)

    def test_counts_multiple_playgroups_in_same_month_separately(self):
        """Should count each qualifying (month, playgroup) pair."""
        playgroup2 = Playgroup.objects.create(name='PG2', slug='pg2')

        for i in range(4):
            event1 = self.create_event(
                date(2025, 1, i + 1),
                playgroup=self.playgroup
            )
            self.create_result(event1)

            event2 = self.create_event(
                date(2025, 1, i + 10),
                playgroup=playgroup2
            )
            self.create_result(event2)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.events_at_group_in_calendar_month
        )
        self.assertEqual(value, 2)

    def test_counts_different_months_separately(self):
        """Should count qualifying months across different months."""
        for i in range(4):
            jan_event = self.create_event(
                date(2025, 1, i + 1),
                playgroup=self.playgroup
            )
            self.create_result(jan_event)

            feb_event = self.create_event(
                date(2025, 2, i + 1),
                playgroup=self.playgroup
            )
            self.create_result(feb_event)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.events_at_group_in_calendar_month
        )
        self.assertEqual(value, 2)


class HouseCriteriaTests(AwardCriteriaTestBase):
    """Tests for criteria 22: tournament_match_wins_with_house."""

    def setUp(self):
        super().setUp()
        self.house_brobnar = House.objects.create(name='Brobnar', src='http://example.com')
        self.house_logos = House.objects.create(name='Logos', src='http://example.com')
        self.set = Set.objects.create(id=1, name='Test Set', src='http://example.com')

    def test_counts_wins_with_specific_house(self):
        """Should count tournament match wins with decks containing the house."""
        deck = Deck.objects.create(
            id=uuid.uuid4(),
            name='Test Deck',
            house_1=self.house_brobnar,
            house_2=self.house_logos,
            set=self.set
        )

        event = self.create_event(date(2025, 1, 1), is_casual=False)
        result = self.create_result(event, num_wins=5, num_losses=2)
        EventResultDeck.objects.create(
            event_result=result,
            deck=deck,
            was_played=True
        )

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.tournament_match_wins_with_house,
            house=self.house_brobnar
        )
        self.assertEqual(value, 5)

    def test_does_not_count_wins_without_house(self):
        """Should not count wins with decks not containing the house."""
        deck = Deck.objects.create(
            id=uuid.uuid4(),
            name='Test Deck',
            house_1=self.house_logos,
            set=self.set
        )

        event = self.create_event(date(2025, 1, 1), is_casual=False)
        result = self.create_result(event, num_wins=5, num_losses=2)
        EventResultDeck.objects.create(
            event_result=result,
            deck=deck,
            was_played=True
        )

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.tournament_match_wins_with_house,
            house=self.house_brobnar
        )
        self.assertEqual(value, 0)

    def test_does_not_count_unplayed_decks(self):
        """Should not count wins from decks marked as not played."""
        deck = Deck.objects.create(
            id=uuid.uuid4(),
            name='Test Deck',
            house_1=self.house_brobnar,
            set=self.set
        )

        event = self.create_event(date(2025, 1, 1), is_casual=False)
        result = self.create_result(event, num_wins=5, num_losses=2)
        EventResultDeck.objects.create(
            event_result=result,
            deck=deck,
            was_played=False
        )

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.tournament_match_wins_with_house,
            house=self.house_brobnar
        )
        self.assertEqual(value, 0)

    def test_counts_house_in_any_slot(self):
        """Should count house in any of the three deck slots."""
        for house_slot in [1, 2, 3]:
            deck_kwargs = {
                'id': uuid.uuid4(),
                'name': f'Deck {house_slot}',
                'set': self.set,
                f'house_{house_slot}': self.house_brobnar
            }
            deck = Deck.objects.create(**deck_kwargs)

            event = self.create_event(date(2025, 1, house_slot), is_casual=False)
            result = self.create_result(event, num_wins=3, num_losses=0)
            EventResultDeck.objects.create(
                event_result=result,
                deck=deck,
                was_played=True
            )

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.tournament_match_wins_with_house,
            house=self.house_brobnar
        )
        self.assertEqual(value, 9)

    def test_does_not_double_count_multiple_decks_same_event(self):
        """Should not double-count wins when multiple decks with house played."""
        deck1 = Deck.objects.create(
            id=uuid.uuid4(),
            name='Deck 1',
            house_1=self.house_brobnar,
            set=self.set
        )
        deck2 = Deck.objects.create(
            id=uuid.uuid4(),
            name='Deck 2',
            house_1=self.house_brobnar,
            set=self.set
        )

        event = self.create_event(date(2025, 1, 1), is_casual=False)
        result = self.create_result(event, num_wins=5, num_losses=2)
        EventResultDeck.objects.create(event_result=result, deck=deck1, was_played=True)
        EventResultDeck.objects.create(event_result=result, deck=deck2, was_played=True)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.tournament_match_wins_with_house,
            house=self.house_brobnar
        )
        self.assertEqual(value, 5)


class SetCriteriaTests(AwardCriteriaTestBase):
    """Tests for criteria 23: sets_with_ten_tournament_match_wins."""

    def setUp(self):
        super().setUp()
        self.set1 = Set.objects.create(id=1, name='Set 1', src='http://example.com')
        self.set2 = Set.objects.create(id=2, name='Set 2', src='http://example.com')

    def test_counts_sets_with_10_plus_wins(self):
        """Should count sets with 10+ total tournament match wins."""
        deck1 = Deck.objects.create(id=uuid.uuid4(), name='Deck 1', set=self.set1)
        deck2 = Deck.objects.create(id=uuid.uuid4(), name='Deck 2', set=self.set1)

        event1 = self.create_event(date(2025, 1, 1), is_casual=False)
        result1 = self.create_result(event1, num_wins=6, num_losses=0)
        EventResultDeck.objects.create(event_result=result1, deck=deck1, was_played=True)

        event2 = self.create_event(date(2025, 1, 2), is_casual=False)
        result2 = self.create_result(event2, num_wins=4, num_losses=0)
        EventResultDeck.objects.create(event_result=result2, deck=deck2, was_played=True)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.sets_with_ten_tournament_match_wins
        )
        self.assertEqual(value, 1)

    def test_does_not_count_sets_with_less_than_10_wins(self):
        """Should not count sets with fewer than 10 wins."""
        deck = Deck.objects.create(id=uuid.uuid4(), name='Deck 1', set=self.set1)

        event = self.create_event(date(2025, 1, 1), is_casual=False)
        result = self.create_result(event, num_wins=9, num_losses=0)
        EventResultDeck.objects.create(event_result=result, deck=deck, was_played=True)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.sets_with_ten_tournament_match_wins
        )
        self.assertEqual(value, 0)

    def test_counts_multiple_sets_separately(self):
        """Should count each qualifying set separately."""
        deck1 = Deck.objects.create(id=uuid.uuid4(), name='Deck 1', set=self.set1)
        deck2 = Deck.objects.create(id=uuid.uuid4(), name='Deck 2', set=self.set2)

        for deck in [deck1, deck2]:
            for i in range(2):
                event = self.create_event(date(2025, 1, i + 1), is_casual=False)
                result = self.create_result(event, num_wins=5, num_losses=0)
                EventResultDeck.objects.create(event_result=result, deck=deck, was_played=True)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.sets_with_ten_tournament_match_wins
        )
        self.assertEqual(value, 2)

    def test_excludes_casual_events(self):
        """Should only count tournament wins, not casual event wins."""
        deck = Deck.objects.create(id=uuid.uuid4(), name='Deck 1', set=self.set1)

        casual = self.create_event(date(2025, 1, 1), is_casual=True)
        casual_result = self.create_result(casual, num_wins=10, num_losses=0)
        EventResultDeck.objects.create(event_result=casual_result, deck=deck, was_played=True)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.sets_with_ten_tournament_match_wins
        )
        self.assertEqual(value, 0)


class PremierTournamentCriteriaTests(AwardCriteriaTestBase):
    """Tests for criteria 37: participate_in_premier_tournament."""

    def test_counts_premier_tournament_participations(self):
        """Should count participations in Premier Tournaments playgroup."""
        premier_event = self.create_event(
            date(2025, 1, 1),
            is_casual=False,
            playgroup=self.premier_playgroup
        )
        self.create_result(premier_event)

        regular_event = self.create_event(
            date(2025, 1, 2),
            is_casual=False,
            playgroup=self.playgroup
        )
        self.create_result(regular_event)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.participate_in_premier_tournament
        )
        self.assertEqual(value, 1)

    def test_excludes_casual_premier_events(self):
        """Should exclude casual events even in Premier Tournaments playgroup."""
        premier_casual = self.create_event(
            date(2025, 1, 1),
            is_casual=True,
            playgroup=self.premier_playgroup
        )
        self.create_result(premier_casual)

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.participate_in_premier_tournament
        )
        self.assertEqual(value, 0)


class LeaderboardCriteriaTests(AwardCriteriaTestBase):
    """Tests for leaderboard ranking criteria (24-36)."""

    def setUp(self):
        super().setUp()
        self.season_leaderboard = Leaderboard.objects.create(
            name='Season',
            sort_order=1,
            period_frequency=LeaderboardSeasonPeriod.FrequencyOptions.SEASON
        )
        self.monthly_leaderboard = Leaderboard.objects.create(
            name='Month',
            sort_order=2,
            period_frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH
        )
        self.season = LeaderboardSeason.objects.create(name='2024-2025', sort_order=1)
        self.period = LeaderboardSeasonPeriod.objects.create(
            name='2024-2025',
            start_date=date(2024, 12, 1),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.SEASON
        )

    def test_playgroup_season_first_place(self):
        """Criteria 24: Should count 1st place finishes on playgroup season leaderboards."""
        PlayerRank.objects.create(
            user=self.user,
            playgroup=self.playgroup,
            rank=1,
            leaderboard=self.season_leaderboard,
            period=self.period,
            total_points=100,
            num_results=5
        )

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_first_place
        )
        self.assertEqual(value, 1)

    def test_playgroup_season_excludes_premier_playgroup(self):
        """Playgroup season criteria should exclude Premier Tournaments playgroup."""
        PlayerRank.objects.create(
            user=self.user,
            playgroup=self.premier_playgroup,
            rank=1,
            leaderboard=self.season_leaderboard,
            period=self.period,
            total_points=100,
            num_results=5
        )

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_first_place
        )
        self.assertEqual(value, 0)

    def test_playgroup_season_top_five_requires_min_players(self):
        """Criteria 27: Should require minimum 10 players for top 5."""
        PlayerRank.objects.create(
            user=self.user,
            playgroup=self.playgroup,
            rank=5,
            leaderboard=self.season_leaderboard,
            period=self.period,
            total_points=80,
            num_results=5
        )

        for i in range(8):
            other_user = User.objects.create_user(username=f'user{i}')
            PlayerRank.objects.create(
                user=other_user,
                playgroup=self.playgroup,
                rank=i + 6,
                leaderboard=self.season_leaderboard,
                period=self.period,
                total_points=50,
                num_results=3
            )

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_top_five
        )
        self.assertEqual(value, 0)

        PlayerRank.objects.create(
            user=User.objects.create_user(username='user9'),
            playgroup=self.playgroup,
            rank=14,
            leaderboard=self.season_leaderboard,
            period=self.period,
            total_points=30,
            num_results=2
        )

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_top_five
        )
        self.assertEqual(value, 1)

    def test_global_monthly_first_place(self):
        """Criteria 33: Should count 1st place on global monthly leaderboard."""
        monthly_period = LeaderboardSeasonPeriod.objects.create(
            name='January 2025',
            start_date=date(2025, 1, 1),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH
        )

        PlayerRank.objects.create(
            user=self.user,
            playgroup=None,
            rank=1,
            leaderboard=self.monthly_leaderboard,
            period=monthly_period,
            total_points=100,
            num_results=5
        )

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.global_leaderboard_monthly_first_place
        )
        self.assertEqual(value, 1)

    def test_global_season_top_ten(self):
        """Criteria 30: Should count 2nd-10th place on global season leaderboard."""
        PlayerRank.objects.create(
            user=self.user,
            playgroup=None,
            rank=5,
            leaderboard=self.season_leaderboard,
            period=self.period,
            total_points=100,
            num_results=5
        )

        value = self.get_criteria_value(
            AwardBase.CriteriaTypeOptions.global_leaderboard_season_top_ten
        )
        self.assertEqual(value, 1)


class AwardCreditTests(AwardCriteriaTestBase):
    """Tests for manual award credits added to criteria values."""

    def test_award_credit_adds_to_criteria_value(self):
        """Award credits should add to the calculated criteria value."""
        event = self.create_event(date(2025, 1, 1))
        self.create_result(event, num_wins=3, num_losses=2)

        AwardCredit.objects.create(
            user=self.user,
            criteria=AwardBase.CriteriaTypeOptions.event_matches,
            amount=10,
            notes='Manual adjustment'
        )

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.event_matches)
        self.assertEqual(value, 15)

    def test_multiple_award_credits_sum(self):
        """Multiple award credits should sum together."""
        AwardCredit.objects.create(
            user=self.user,
            criteria=AwardBase.CriteriaTypeOptions.events,
            amount=5
        )
        AwardCredit.objects.create(
            user=self.user,
            criteria=AwardBase.CriteriaTypeOptions.events,
            amount=3
        )

        value = self.get_criteria_value(AwardBase.CriteriaTypeOptions.events)
        self.assertEqual(value, 8)
