from allauth.account.models import EmailAddress
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from datetime import date, timedelta
from .models import (
    Event, EventResult, RankingPoints, Leaderboard, LeaderboardSeason,
    LeaderboardSeasonPeriod, PlayerRank, Playgroup, PlaygroupEvent,
    RankingPointsMapVersion, RankingPointsMap, RankingPointsService,
    EventFormat, AwardBase, Achievement, Trophy, AwardAssignmentService,
    EventResultDeck, AwardCredit, LevelBreakpoint, AchievementTier,
    PlaygroupQuerySet, PlaygroupVenue, Venue, PlaygroupMember, Avatar,
    get_activity_level
)
from .models import Ladder, LadderChallenge, LadderRuleViolation
from .models import Feature, PlaygroupFeature
from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from .forms import PmcProfileForm, PmcProfilePrivacyForm
from .templatetags.pmc_extras import relative_event_day
from django.urls import reverse
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
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.SEASON,
            is_locked=True
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
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH,
            is_locked=True
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


class LeaderboardPeriodLockingTest(TestCase):

    def setUp(self):
        self.season = LeaderboardSeason.objects.create(name='Test Season')

    def test_should_be_locked_returns_true_for_old_periods(self):
        old_period = LeaderboardSeasonPeriod.objects.create(
            name='January 2025',
            start_date=date.today() - timedelta(days=40),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH
        )

        next_period = LeaderboardSeasonPeriod.objects.create(
            name='February 2025',
            start_date=date.today() - timedelta(days=10),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH
        )

        self.assertTrue(old_period.should_be_locked())

    def test_should_be_locked_returns_false_for_recent_periods(self):
        recent_period = LeaderboardSeasonPeriod.objects.create(
            name='Recent Period',
            start_date=date.today() - timedelta(days=5),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH
        )

        self.assertFalse(recent_period.should_be_locked())

    def test_should_be_locked_returns_false_for_current_periods(self):
        current_period = LeaderboardSeasonPeriod.objects.create(
            name='Current Period',
            start_date=date.today(),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH
        )

        self.assertFalse(current_period.should_be_locked())

    def test_should_be_locked_returns_false_for_all_time_periods(self):
        all_time_period = LeaderboardSeasonPeriod.objects.create(
            name='All Time',
            start_date=date.today() - timedelta(days=365),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.ALL_TIME
        )

        self.assertFalse(all_time_period.should_be_locked())

    def test_update_lock_status_locks_old_period(self):
        old_period = LeaderboardSeasonPeriod.objects.create(
            name='January 2025',
            start_date=date.today() - timedelta(days=40),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH,
            is_locked=False
        )

        next_period = LeaderboardSeasonPeriod.objects.create(
            name='February 2025',
            start_date=date.today() - timedelta(days=10),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH
        )

        result = old_period.update_lock_status()

        self.assertTrue(result)
        old_period.refresh_from_db()
        self.assertTrue(old_period.is_locked)

    def test_update_lock_status_is_idempotent(self):
        old_period = LeaderboardSeasonPeriod.objects.create(
            name='January 2025',
            start_date=date.today() - timedelta(days=40),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH,
            is_locked=False
        )

        next_period = LeaderboardSeasonPeriod.objects.create(
            name='February 2025',
            start_date=date.today() - timedelta(days=10),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH
        )

        result1 = old_period.update_lock_status()
        self.assertTrue(result1)

        result2 = old_period.update_lock_status()
        self.assertFalse(result2)

        old_period.refresh_from_db()
        self.assertTrue(old_period.is_locked)

    def test_update_lock_status_does_not_lock_recent_period(self):
        recent_period = LeaderboardSeasonPeriod.objects.create(
            name='Recent Period',
            start_date=date.today() - timedelta(days=5),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH,
            is_locked=False
        )

        result = recent_period.update_lock_status()

        self.assertFalse(result)
        recent_period.refresh_from_db()
        self.assertFalse(recent_period.is_locked)

    def test_manager_update_all_lock_statuses(self):
        old_period1 = LeaderboardSeasonPeriod.objects.create(
            name='Old Period 1',
            start_date=date.today() - timedelta(days=60),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH,
            is_locked=False
        )

        old_period2 = LeaderboardSeasonPeriod.objects.create(
            name='Old Period 2',
            start_date=date.today() - timedelta(days=40),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH,
            is_locked=False
        )

        recent_period = LeaderboardSeasonPeriod.objects.create(
            name='Recent Period',
            start_date=date.today() - timedelta(days=10),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH,
            is_locked=False
        )

        current_period = LeaderboardSeasonPeriod.objects.create(
            name='Current Period',
            start_date=date.today(),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH,
            is_locked=False
        )

        count = LeaderboardSeasonPeriod.objects.update_all_lock_statuses()

        self.assertEqual(count, 2)

        old_period1.refresh_from_db()
        old_period2.refresh_from_db()
        recent_period.refresh_from_db()
        current_period.refresh_from_db()

        self.assertTrue(old_period1.is_locked)
        self.assertTrue(old_period2.is_locked)
        self.assertFalse(recent_period.is_locked)
        self.assertFalse(current_period.is_locked)

    def test_manager_excludes_all_time_periods_from_locking(self):
        all_time_period = LeaderboardSeasonPeriod.objects.create(
            name='All Time',
            start_date=date.today() - timedelta(days=365),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.ALL_TIME,
            is_locked=False
        )

        count = LeaderboardSeasonPeriod.objects.update_all_lock_statuses()

        self.assertEqual(count, 0)

        all_time_period.refresh_from_db()
        self.assertFalse(all_time_period.is_locked)

    def test_get_end_date_returns_next_period_start_date(self):
        period1 = LeaderboardSeasonPeriod.objects.create(
            name='Period 1',
            start_date=date(2025, 1, 1),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH
        )

        period2 = LeaderboardSeasonPeriod.objects.create(
            name='Period 2',
            start_date=date(2025, 2, 1),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH
        )

        end_date = period1.get_end_date()
        self.assertEqual(end_date, date(2025, 2, 1))

    def test_get_end_date_returns_tomorrow_for_latest_period(self):
        period = LeaderboardSeasonPeriod.objects.create(
            name='Latest Period',
            start_date=date.today(),
            season=self.season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH
        )

        end_date = period.get_end_date()
        self.assertEqual(end_date, date.today() + timedelta(days=1))


class UpcomingEventsFilterTestBase(TestCase):
    def setUp(self):
        self.today = date.today()
        self.player = User.objects.create_user(username='finder-player')
        self.playgroup = self.create_playgroup('Finder Group')

    def create_playgroup(self, name, is_global=False):
        return Playgroup.objects.create(
            name=name, slug=name.lower().replace(' ', '-'), is_global=is_global)

    def create_event(self, start_date, playgroup=None, is_digital=False, format_name=None):
        event = Event.objects.create(
            name=f'Event on {start_date}',
            start_date=start_date,
            is_digital=is_digital,
        )
        if format_name:
            event.format, _ = EventFormat.objects.get_or_create(
                name=format_name)
            event.save()
        PlaygroupEvent.objects.create(
            playgroup=playgroup or self.playgroup, event=event)
        return event

    def register_player(self, event, finishing_position=None):
        return EventResult.objects.create(
            event=event, user=self.player, finishing_position=finishing_position)

    def add_mappable_venue(self, playgroup):
        venue = Venue.objects.create(
            name=f'{playgroup.name} Venue',
            slug=f'{playgroup.slug}-venue',
            address='1 Main St',
            latitude=43.68,
            longitude=-70.35,
            city='Westbrook',
            state_province='Maine',
            country='United States',
        )
        PlaygroupVenue.objects.create(playgroup=playgroup, venue=venue)
        return venue


class PlaygroupHostingUpcomingEventsTests(UpcomingEventsFilterTestBase):
    def playgroups_hosting_upcoming_events(self, **filters):
        return list(Playgroup.objects.hosting_events(upcoming_only=True, **filters))

    def test_includes_event_starting_today(self):
        self.create_event(self.today)
        self.assertEqual(self.playgroups_hosting_upcoming_events(), [
                         self.playgroup])

    def test_includes_event_from_yesterday_without_finished_results(self):
        self.create_event(self.today - timedelta(days=1))
        self.assertEqual(self.playgroups_hosting_upcoming_events(), [
                         self.playgroup])

    def test_excludes_event_older_than_yesterday(self):
        self.create_event(self.today - timedelta(days=2))
        self.assertEqual(self.playgroups_hosting_upcoming_events(), [])

    def test_includes_future_event_with_registrations_only(self):
        event = self.create_event(self.today + timedelta(days=7))
        self.register_player(event)
        self.assertEqual(self.playgroups_hosting_upcoming_events(), [
                         self.playgroup])

    def test_excludes_future_event_with_finished_results(self):
        event = self.create_event(self.today + timedelta(days=7))
        self.register_player(event, finishing_position=1)
        self.assertEqual(self.playgroups_hosting_upcoming_events(), [])

    def test_excludes_playgroup_without_events(self):
        self.assertEqual(self.playgroups_hosting_upcoming_events(), [])

    def test_does_not_count_events_from_other_playgroups(self):
        other_playgroup = self.create_playgroup('Other Group')
        self.create_event(self.today + timedelta(days=7),
                          playgroup=other_playgroup)
        self.assertEqual(self.playgroups_hosting_upcoming_events(), [
                         other_playgroup])

    def test_returns_playgroup_once_with_multiple_upcoming_events(self):
        self.create_event(self.today + timedelta(days=7))
        self.create_event(self.today + timedelta(days=14))
        self.assertEqual(self.playgroups_hosting_upcoming_events(), [
                         self.playgroup])

    def test_format_and_upcoming_must_match_the_same_event(self):
        self.create_event(self.today - timedelta(days=30), format_name='Archon')
        self.create_event(self.today + timedelta(days=7), format_name='Sealed')
        archon = EventFormat.objects.get(name='Archon')
        self.assertEqual(
            self.playgroups_hosting_upcoming_events(event_format=archon.id), [])

    def test_matches_upcoming_event_of_requested_format(self):
        self.create_event(self.today + timedelta(days=7), format_name='Archon')
        archon = EventFormat.objects.get(name='Archon')
        self.assertEqual(
            self.playgroups_hosting_upcoming_events(event_format=archon.id), [self.playgroup])

    def test_unformatted_filter_matches_only_upcoming_unformatted_events(self):
        self.create_event(self.today - timedelta(days=30))
        self.create_event(self.today + timedelta(days=7), format_name='Archon')
        self.assertEqual(
            self.playgroups_hosting_upcoming_events(
                event_format=PlaygroupQuerySet.UNFORMATTED_EVENT_FORMAT),
            [])

    def test_in_person_filter_ignores_upcoming_digital_events(self):
        self.create_event(self.today + timedelta(days=7), is_digital=True)
        self.assertEqual(
            self.playgroups_hosting_upcoming_events(is_digital=False), [])

    def test_unrestricted_mode_counts_upcoming_digital_events(self):
        self.create_event(self.today + timedelta(days=7), is_digital=True)
        self.assertEqual(self.playgroups_hosting_upcoming_events(), [
                         self.playgroup])


class FinderMapUpcomingEventsTests(UpcomingEventsFilterTestBase):
    def setUp(self):
        super().setUp()
        self.add_mappable_venue(self.playgroup)

    def fetch_playgroup_names(self, **params):
        response = self.client.get(reverse('pmc-finder-data'), params)
        self.assertEqual(response.status_code, 200)
        return [playgroup['name'] for playgroup in response.json()['playgroups']]

    def test_includes_playgroup_with_upcoming_in_person_event(self):
        self.create_event(self.today + timedelta(days=7))
        self.assertEqual(self.fetch_playgroup_names(
            upcoming_events='1'), ['Finder Group'])

    def test_excludes_playgroup_with_only_past_events(self):
        self.create_event(self.today - timedelta(days=30))
        self.assertEqual(self.fetch_playgroup_names(upcoming_events='1'), [])
        self.assertEqual(self.fetch_playgroup_names(), ['Finder Group'])

    def test_excludes_playgroup_with_only_upcoming_digital_events(self):
        self.create_event(self.today + timedelta(days=7), is_digital=True)
        self.assertEqual(self.fetch_playgroup_names(upcoming_events='1'), [])

    def test_excludes_global_playgroup_with_upcoming_event(self):
        global_playgroup = self.create_playgroup(
            'Global Group', is_global=True)
        self.add_mappable_venue(global_playgroup)
        self.create_event(self.today + timedelta(days=7),
                          playgroup=global_playgroup)
        self.assertEqual(self.fetch_playgroup_names(upcoming_events='1'), [])

    def test_ignores_unchecked_upcoming_value(self):
        self.assertEqual(self.fetch_playgroup_names(
            upcoming_events='0'), ['Finder Group'])


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class FinderTableUpcomingEventsTests(UpcomingEventsFilterTestBase):
    def fetch_playgroup_names(self, **params):
        response = self.client.get(reverse('pmc-finder-table'), params)
        self.assertEqual(response.status_code, 200)
        return [playgroup.name for playgroup in response.context['page_obj']]

    def test_includes_playgroup_without_venue_hosting_upcoming_event(self):
        self.create_event(self.today + timedelta(days=7), is_digital=True)
        self.assertEqual(self.fetch_playgroup_names(
            upcoming_events='1'), ['Finder Group'])

    def test_excludes_playgroup_with_only_finished_events(self):
        event = self.create_event(self.today)
        self.register_player(event, finishing_position=1)
        self.assertEqual(self.fetch_playgroup_names(upcoming_events='1'), [])

    def test_digital_mode_requires_upcoming_digital_event(self):
        for _ in range(2):
            self.create_event(self.today - timedelta(days=30), is_digital=True)
        self.create_event(self.today + timedelta(days=7))
        self.assertEqual(self.fetch_playgroup_names(
            mode='digital', upcoming_events='1'), [])
        self.assertEqual(self.fetch_playgroup_names(
            mode='digital'), ['Finder Group'])

    def test_in_person_mode_requires_upcoming_in_person_event(self):
        self.create_event(self.today - timedelta(days=30))
        self.create_event(self.today + timedelta(days=7), is_digital=True)
        self.assertEqual(self.fetch_playgroup_names(
            mode='in_person', upcoming_events='1'), [])


class PlaygroupNextUpcomingEventAnnotationTests(UpcomingEventsFilterTestBase):
    def annotated_playgroup(self, **filters):
        return Playgroup.objects.annotate_next_upcoming_event(**filters).get(pk=self.playgroup.pk)

    def test_is_empty_without_upcoming_events(self):
        self.create_event(self.today - timedelta(days=30))
        playgroup = self.annotated_playgroup()
        self.assertIsNone(playgroup.next_event_date)
        self.assertIsNone(playgroup.next_event_format_name)

    def test_picks_earliest_upcoming_event_and_its_format(self):
        self.create_event(self.today + timedelta(days=14), format_name='Sealed')
        self.create_event(self.today + timedelta(days=3), format_name='Archon')
        playgroup = self.annotated_playgroup()
        self.assertEqual(playgroup.next_event_date,
                         self.today + timedelta(days=3))
        self.assertEqual(playgroup.next_event_format_name, 'Archon')

    def test_skips_event_with_finished_results(self):
        finished_event = self.create_event(self.today)
        self.register_player(finished_event, finishing_position=1)
        self.create_event(self.today + timedelta(days=5))
        self.assertEqual(self.annotated_playgroup().next_event_date,
                         self.today + timedelta(days=5))

    def test_respects_requested_mode(self):
        self.create_event(self.today + timedelta(days=2), is_digital=True)
        self.create_event(self.today + timedelta(days=9))
        self.assertEqual(
            self.annotated_playgroup(is_digital=False).next_event_date,
            self.today + timedelta(days=9))
        self.assertEqual(
            self.annotated_playgroup(is_digital=True).next_event_date,
            self.today + timedelta(days=2))


class PlaygroupRecentActivityAnnotationTests(UpcomingEventsFilterTestBase):
    def events_last_90_days(self):
        return Playgroup.objects.annotate_recent_activity().get(pk=self.playgroup.pk).events_last_90_days

    def test_is_zero_without_events(self):
        self.assertEqual(self.events_last_90_days(), 0)

    def test_counts_events_within_window_inclusive(self):
        self.create_event(self.today)
        self.create_event(self.today - timedelta(days=90))
        self.assertEqual(self.events_last_90_days(), 2)

    def test_ignores_events_outside_window_and_future_events(self):
        self.create_event(self.today - timedelta(days=91))
        self.create_event(self.today + timedelta(days=1))
        self.assertEqual(self.events_last_90_days(), 0)

    def test_ignores_events_from_other_playgroups(self):
        self.create_event(self.today, playgroup=self.create_playgroup('Other Group'))
        self.assertEqual(self.events_last_90_days(), 0)

    def test_activity_levels_celebrate_recent_events(self):
        self.assertEqual(
            [get_activity_level(count).slug for count in (1, 3, 4, 8, 9)],
            ['active', 'active', 'busy', 'busy', 'blazing'])

    def test_no_activity_level_without_recent_events(self):
        self.assertIsNone(get_activity_level(0))

    def test_last_event_date_is_most_recent_held_event(self):
        self.create_event(self.today - timedelta(days=200))
        self.create_event(self.today - timedelta(days=120))
        self.create_event(self.today + timedelta(days=3))
        playgroup = Playgroup.objects.annotate_recent_activity().get(pk=self.playgroup.pk)
        self.assertEqual(playgroup.last_event_date, self.today - timedelta(days=120))

    def test_last_event_date_is_empty_without_held_events(self):
        self.create_event(self.today + timedelta(days=3))
        playgroup = Playgroup.objects.annotate_recent_activity().get(pk=self.playgroup.pk)
        self.assertIsNone(playgroup.last_event_date)


class RelativeEventDayFilterTests(TestCase):
    def test_uses_natural_words_near_today(self):
        today = date.today()
        self.assertEqual(relative_event_day(today), 'today')
        self.assertEqual(relative_event_day(today + timedelta(days=1)), 'tomorrow')

    def test_counts_days_within_the_week(self):
        self.assertEqual(relative_event_day(date.today() + timedelta(days=3)), 'in 3 days')

    def test_falls_back_to_short_date(self):
        event_day = date.today() + timedelta(days=10)
        self.assertEqual(relative_event_day(event_day), event_day.strftime('%a, %b ') + str(event_day.day))

    def test_counts_up_to_six_days_then_uses_date(self):
        six_days_out = date.today() + timedelta(days=6)
        seven_days_out = date.today() + timedelta(days=7)
        self.assertEqual(relative_event_day(six_days_out), 'in 6 days')
        self.assertEqual(relative_event_day(seven_days_out),
                         seven_days_out.strftime('%a, %b ') + str(seven_days_out.day))

    def test_uses_date_for_unfinished_event_from_yesterday(self):
        yesterday = date.today() - timedelta(days=1)
        self.assertEqual(relative_event_day(yesterday),
                         yesterday.strftime('%a, %b ') + str(yesterday.day))


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class FinderGroupCardTests(UpcomingEventsFilterTestBase):
    def setUp(self):
        super().setUp()
        self.default_avatar = self.create_avatar('001')

    def create_avatar(self, pmc_id):
        return Avatar.objects.create(
            pmc_id=pmc_id,
            src=f'https://example.com/avatar-{pmc_id}.png',
            category_label='Test',
            name=f'Avatar {pmc_id}',
            banner_bg_color='000000',
            banner_stroke_color='000000',
        )

    def add_member(self, username, is_hidden=False, shows_playgroups=True, avatar=None):
        user = User.objects.create_user(username=username)
        user.pmc_profile.show_playgroups_on_profile = shows_playgroups
        user.pmc_profile.avatar = avatar
        user.pmc_profile.save()
        PlaygroupMember.objects.create(
            playgroup=self.playgroup, user=user, is_hidden=is_hidden)
        return user

    def fetch_card(self, slug=None):
        return self.client.get(reverse('pmc-finder-card', args=[slug or self.playgroup.slug]))

    def test_only_shows_avatars_of_visible_opted_in_members(self):
        self.add_member('visible', avatar=self.create_avatar('101'))
        self.add_member('hidden', is_hidden=True, avatar=self.create_avatar('102'))
        self.add_member('private', shows_playgroups=False, avatar=self.create_avatar('103'))
        response = self.fetch_card()
        self.assertEqual(response.context['member_avatar_srcs'], [
                         'https://example.com/avatar-101.png'])
        self.assertEqual(response.context['hidden_member_avatar_count'], 0)

    def test_uses_default_avatar_and_counts_overflow(self):
        for index in range(7):
            self.add_member(f'member-{index}')
        response = self.fetch_card()
        self.assertEqual(len(response.context['member_avatar_srcs']), 5)
        self.assertEqual(response.context['member_avatar_srcs'][0], self.default_avatar.src)
        self.assertEqual(response.context['hidden_member_avatar_count'], 2)

    def test_lists_upcoming_events_only(self):
        self.create_event(self.today - timedelta(days=10))
        upcoming = self.create_event(self.today + timedelta(days=3))
        response = self.fetch_card()
        self.assertEqual(list(response.context['upcoming_events']), [upcoming])

    def test_offers_join_to_anonymous_visitors(self):
        response = self.fetch_card()
        self.assertContains(response, reverse('pmc-pg-join', args=[self.playgroup.slug]))

    def test_shows_member_badge_to_members(self):
        member = self.add_member('member')
        self.client.force_login(member)
        response = self.fetch_card()
        self.assertTrue(response.context['is_member'])
        self.assertNotContains(response, reverse('pmc-pg-join', args=[self.playgroup.slug]))

    def test_global_playgroups_are_not_found(self):
        global_playgroup = self.create_playgroup('Global Group', is_global=True)
        self.assertEqual(self.fetch_card(global_playgroup.slug).status_code, 404)


class FinderMapGroupDetailsTests(UpcomingEventsFilterTestBase):
    def setUp(self):
        super().setUp()
        self.add_mappable_venue(self.playgroup)

    def fetch_only_playgroup(self, **params):
        response = self.client.get(reverse('pmc-finder-data'), params)
        self.assertEqual(response.status_code, 200)
        [playgroup] = response.json()['playgroups']
        return playgroup

    def test_includes_card_url_and_activity_level(self):
        self.create_event(self.today - timedelta(days=5))
        playgroup = self.fetch_only_playgroup()
        self.assertEqual(playgroup['card_url'], reverse(
            'pmc-finder-card', args=[self.playgroup.slug]))
        self.assertEqual(playgroup['activity_level'], 'active')

    def test_next_event_is_earliest_in_person_upcoming_event(self):
        self.create_event(self.today + timedelta(days=1), is_digital=True)
        self.create_event(self.today + timedelta(days=4), format_name='Archon')
        self.assertEqual(self.fetch_only_playgroup()['next_event'], {
            'date': (self.today + timedelta(days=4)).isoformat(),
            'format': 'Archon',
        })

    def test_next_event_is_empty_without_upcoming_events(self):
        self.assertIsNone(self.fetch_only_playgroup()['next_event'])

    def test_activity_level_is_empty_without_recent_events(self):
        self.create_event(self.today - timedelta(days=120))
        self.assertIsNone(self.fetch_only_playgroup()['activity_level'])

    def test_next_event_respects_format_filter(self):
        self.create_event(self.today + timedelta(days=1), format_name='Archon')
        self.create_event(self.today + timedelta(days=5), format_name='Sealed')
        sealed = EventFormat.objects.get(name='Sealed')
        self.assertEqual(
            self.fetch_only_playgroup(event_format=sealed.id)['next_event']['date'],
            (self.today + timedelta(days=5)).isoformat())


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class FinderTableNextEventTests(UpcomingEventsFilterTestBase):
    def fetch_next_event_dates(self, **params):
        response = self.client.get(reverse('pmc-finder-table'), params)
        self.assertEqual(response.status_code, 200)
        return [playgroup.next_event_date for playgroup in response.context['page_obj']]

    def test_unrestricted_mode_uses_any_upcoming_event(self):
        self.create_event(self.today + timedelta(days=2), is_digital=True)
        self.create_event(self.today + timedelta(days=6))
        self.assertEqual(self.fetch_next_event_dates(), [
                         self.today + timedelta(days=2)])

    def test_in_person_mode_ignores_digital_events(self):
        self.create_event(self.today - timedelta(days=20))
        self.create_event(self.today + timedelta(days=2), is_digital=True)
        self.create_event(self.today + timedelta(days=6))
        self.assertEqual(self.fetch_next_event_dates(mode='in_person'), [
                         self.today + timedelta(days=6)])

    def test_respects_format_filter(self):
        self.create_event(self.today + timedelta(days=1), format_name='Archon')
        self.create_event(self.today + timedelta(days=5), format_name='Sealed')
        sealed = EventFormat.objects.get(name='Sealed')
        self.assertEqual(self.fetch_next_event_dates(event_format=sealed.id), [
                         self.today + timedelta(days=5)])


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class CaseInsensitiveUsernameLookupTests(TestCase):
    def setUp(self):
        self.playgroup = Playgroup.objects.create(name='Lookup Group', slug='lookup-group')
        self.staff_user = User.objects.create_user(username='Organizer')
        PlaygroupMember.objects.create(
            playgroup=self.playgroup, user=self.staff_user, is_staff=True)
        self.player = User.objects.create_user(username='MixedCasePlayer')
        self.client.force_login(self.staff_user)

    def test_user_profile_resolves_username_in_any_case(self):
        response = self.client.get(
            reverse('pmc-user-profile', kwargs={'username': 'mixedcaseplayer'}))
        self.assertEqual(response.status_code, 200)

    def test_add_member_by_username_matches_any_case(self):
        self.client.post(
            reverse('pmc-pg-add-member-by-username', kwargs={'slug': self.playgroup.slug}),
            {'username': 'MIXEDCASEPLAYER'})
        self.assertTrue(PlaygroupMember.objects.filter(
            playgroup=self.playgroup, user=self.player).exists())


class ManageProfileEmailChangeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='Player', email='player@example.com')
        EmailAddress.objects.create(
            user=self.user, email='player@example.com', verified=True, primary=True)
        self.client.force_login(self.user)

    def build_post_data(self, **overrides):
        profile = self.user.pmc_profile
        data = {
            **PmcProfileForm(instance=profile).initial,
            **PmcProfilePrivacyForm(instance=profile).initial,
            'username': self.user.username,
            'email': self.user.email,
        }
        data.update(overrides)
        return {key: '' if value is None else value for key, value in data.items()}

    def test_changing_email_sends_verification_without_switching_email(self):
        response = self.client.post(
            reverse('pmc-my-keychain-manage'),
            self.build_post_data(email='new@example.com'))
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'player@example.com')
        self.assertEqual(EmailAddress.objects.get_new(self.user).email, 'new@example.com')
        self.assertEqual(len(mail.outbox), 1)


class LadderTestBase(TestCase):
    def setUp(self):
        self.playgroup = Playgroup.objects.create(
            name='Ladder Group', slug='ladder-group')
        self.enable_ladders_for(self.playgroup)
        self.organizer = self.create_member('organizer', is_staff=True)
        self.players = [self.create_member(f'player{number}') for number in range(1, 7)]
        self.ladder = Ladder.objects.create(
            playgroup=self.playgroup, name='Main Ladder')
        for player in self.players:
            self.ladder.add_member(player)

    def enable_ladders_for(self, playgroup):
        PlaygroupFeature.objects.create(
            playgroup=playgroup, feature=Feature.objects.get(key=Feature.Keys.LADDERS))

    def create_member(self, username, playgroup=None, is_staff=False):
        user = User.objects.create_user(username=username)
        return PlaygroupMember.objects.create(
            playgroup=playgroup or self.playgroup, user=user, is_staff=is_staff)

    def player(self, number):
        return self.players[number - 1]

    def ranked_usernames(self):
        return [entry.member.user.username for entry in self.ladder.get_ordered_entries()]

    def usernames_for(self, *numbers):
        return [f'player{number}' for number in numbers]

    def assert_positions_contiguous(self):
        positions = list(self.ladder.entries.order_by(
            'position').values_list('position', flat=True))
        self.assertEqual(positions, list(range(1, len(positions) + 1)))

    def make_overdue(self, challenge, days_overdue=1):
        LadderChallenge.objects.filter(pk=challenge.pk).update(
            respond_by=timezone.now() - timedelta(days=days_overdue))

    def allow_open_challenges(self, limit):
        self.ladder.open_challenge_limit = limit
        self.ladder.save()


class LadderMembershipTests(LadderTestBase):
    def test_joining_places_member_at_the_bottom(self):
        newcomer = self.create_member('newcomer')
        self.ladder.add_member(newcomer)
        self.assertEqual(self.ladder.get_rank_of(newcomer), 7)
        self.assert_positions_contiguous()

    def test_joining_twice_is_rejected(self):
        with self.assertRaisesMessage(LadderRuleViolation, 'already on this ladder'):
            self.ladder.add_member(self.player(1))

    def test_member_of_another_playgroup_is_rejected(self):
        other_playgroup = Playgroup.objects.create(name='Other', slug='other')
        outsider = self.create_member('outsider', playgroup=other_playgroup)
        with self.assertRaisesMessage(LadderRuleViolation, 'not a member of this playgroup'):
            self.ladder.add_member(outsider)

    def test_adding_at_a_rank_shifts_lower_players_down(self):
        newcomer = self.create_member('newcomer')
        self.ladder.add_member(newcomer, rank=2)
        self.assertEqual(self.ranked_usernames(), [
            'player1', 'newcomer', 'player2', 'player3', 'player4', 'player5', 'player6'])
        self.assert_positions_contiguous()

    def test_adding_beyond_the_bottom_places_member_last(self):
        newcomer = self.create_member('newcomer')
        self.ladder.add_member(newcomer, rank=50)
        self.assertEqual(self.ladder.get_rank_of(newcomer), 7)

    def test_moving_a_member_up(self):
        self.ladder.move_member(self.player(5), 2)
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 5, 2, 3, 4, 6))
        self.assert_positions_contiguous()

    def test_moving_a_member_down(self):
        self.ladder.move_member(self.player(2), 5)
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 3, 4, 5, 2, 6))
        self.assert_positions_contiguous()

    def test_removing_a_member_closes_the_gap(self):
        self.ladder.remove_member(self.player(3))
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 4, 5, 6))
        self.assert_positions_contiguous()

    def test_removing_a_member_not_on_the_ladder_is_rejected(self):
        with self.assertRaisesMessage(LadderRuleViolation, 'not on this ladder'):
            self.ladder.remove_member(self.organizer)

    def test_leaving_withdraws_issued_and_voids_received_challenges(self):
        self.allow_open_challenges(2)
        issued = self.ladder.issue_challenge(self.player(4), self.player(3))
        received = self.ladder.issue_challenge(self.player(5), self.player(4))

        self.ladder.remove_member(self.player(4))

        issued.refresh_from_db()
        received.refresh_from_db()
        self.assertEqual(issued.status, LadderChallenge.ChallengeStatuses.WITHDRAWN)
        self.assertEqual(received.status, LadderChallenge.ChallengeStatuses.VOIDED)

    def test_deleted_playgroup_member_drops_off_and_ranks_stay_sequential(self):
        self.player(2).delete()
        self.assertEqual(self.ladder.get_rank_of(self.player(3)), 2)
        self.ladder.move_member(self.player(6), 1)
        self.assert_positions_contiguous()


class LadderChallengeEligibilityTests(LadderTestBase):
    def assert_challenge_rejected(self, challenger, defender, message):
        self.assertIn(message, str(
            self.ladder.get_challenge_ineligibility_reason(challenger, defender)))
        with self.assertRaisesMessage(LadderRuleViolation, message):
            self.ladder.issue_challenge(challenger, defender)

    def test_challenges_disabled(self):
        self.ladder.challenges_enabled = False
        self.ladder.save()
        self.assert_challenge_rejected(
            self.player(2), self.player(1), 'Challenges are disabled')

    def test_challenger_must_be_on_the_ladder(self):
        self.assert_challenge_rejected(
            self.organizer, self.player(6), 'Join the ladder')

    def test_defender_must_be_on_the_ladder(self):
        self.assert_challenge_rejected(
            self.player(6), self.organizer, 'not on this ladder')

    def test_cannot_challenge_self(self):
        self.assert_challenge_rejected(
            self.player(3), self.player(3), 'cannot challenge yourself')

    def test_cannot_challenge_players_ranked_below(self):
        self.assert_challenge_rejected(
            self.player(2), self.player(3), 'ranked above you')

    def test_challenge_at_the_edge_of_range_is_allowed(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(1))
        self.assertTrue(challenge.is_pending())

    def test_challenge_beyond_range_is_rejected(self):
        self.assert_challenge_rejected(
            self.player(5), self.player(1), 'up to 3 places above you')

    def test_challenger_at_open_challenge_limit_is_rejected(self):
        self.ladder.issue_challenge(self.player(4), self.player(3))
        self.assert_challenge_rejected(
            self.player(4), self.player(2), 'reached your limit')

    def test_defender_at_open_challenge_limit_is_rejected(self):
        self.ladder.issue_challenge(self.player(4), self.player(3))
        self.assert_challenge_rejected(
            self.player(5), self.player(3), 'player3 has reached their limit')

    def test_received_challenges_count_toward_the_limit(self):
        self.ladder.issue_challenge(self.player(4), self.player(3))
        self.assert_challenge_rejected(
            self.player(3), self.player(2), 'reached your limit')

    def test_duplicate_open_challenge_is_rejected(self):
        self.allow_open_challenges(2)
        self.ladder.issue_challenge(self.player(4), self.player(3))
        self.assert_challenge_rejected(
            self.player(4), self.player(3), 'already have an open challenge with player3')

    def test_withdrawn_challenge_frees_the_slot(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.ladder.withdraw_challenge(challenge, self.player(4).user)
        self.assertIsNone(self.ladder.get_challenge_ineligibility_reason(
            self.player(4), self.player(2)))

    def test_deadline_is_fixed_when_the_challenge_is_issued(self):
        before_issue = timezone.now()
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.ladder.response_window_days = 30
        self.ladder.save()
        challenge.refresh_from_db()
        self.assertGreaterEqual(challenge.respond_by, before_issue + timedelta(days=7))
        self.assertLess(challenge.respond_by, before_issue + timedelta(days=8))

    def test_standings_only_offer_challenges_within_reach(self):
        standings = self.ladder.get_standings_for(self.player(5))
        challengeable_ranks = [s.rank for s in standings if s.can_be_challenged]
        self.assertEqual(challengeable_ranks, [2, 3, 4])
        self.assertTrue(standings[4].is_viewer)

    def test_standings_explain_why_a_reachable_player_cannot_be_challenged(self):
        self.ladder.issue_challenge(self.player(3), self.player(2))
        standings = self.ladder.get_standings_for(self.player(4))
        self.assertFalse(standings[1].can_be_challenged)
        self.assertIn('reached their limit', str(standings[1].challenge_block_reason))
        self.assertTrue(standings[1].has_open_challenge)


class LadderResultTests(LadderTestBase):
    def test_challenger_win_moves_challenger_directly_ahead_of_defender(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.ladder.record_result(challenge, self.player(5), self.player(5).user)

        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 5, 3, 4, 6))
        self.assert_positions_contiguous()
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, LadderChallenge.ChallengeStatuses.COMPLETED)
        self.assertEqual(challenge.match.result.winner, self.player(5))
        self.assertFalse(challenge.match.result.is_forfeit)

    def test_defender_win_keeps_positions(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.ladder.record_result(challenge, self.player(3), self.player(3).user)
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 3, 4, 5, 6))

    def test_tie_keeps_positions(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.ladder.record_result(challenge, None, self.player(5).user)
        challenge.refresh_from_db()
        self.assertTrue(challenge.match.result.is_tie())
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 3, 4, 5, 6))

    def test_organizer_may_record_a_result(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.ladder.record_result(challenge, self.player(3), self.organizer.user)
        challenge.refresh_from_db()
        self.assertEqual(challenge.match.result.recorded_by, self.organizer.user)

    def test_unrelated_player_cannot_record_a_result(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        with self.assertRaises(PermissionDenied):
            self.ladder.record_result(challenge, self.player(3), self.player(1).user)

    def test_winner_must_be_in_the_match(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        with self.assertRaisesMessage(LadderRuleViolation, 'must be one of the players'):
            self.ladder.record_result(challenge, self.player(1), self.organizer.user)

    def test_resolved_challenge_cannot_be_recorded_again(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.ladder.record_result(challenge, self.player(3), self.player(3).user)
        with self.assertRaisesMessage(LadderRuleViolation, 'already been resolved'):
            self.ladder.record_result(challenge, self.player(5), self.player(5).user)

    def test_result_after_deadline_is_rejected_and_challenger_wins_by_forfeit(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.make_overdue(challenge)

        with self.assertRaisesMessage(LadderRuleViolation, 'won by forfeit'):
            self.ladder.record_result(challenge, self.player(3), self.player(3).user)

        challenge.refresh_from_db()
        self.assertEqual(challenge.status, LadderChallenge.ChallengeStatuses.FORFEITED)
        self.assertTrue(challenge.match.result.is_forfeit)
        self.assertIsNone(challenge.match.result.recorded_by)
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 5, 3, 4, 6))

    def test_challenger_already_ahead_of_defender_does_not_move(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.ladder.move_member(self.player(5), 1)
        self.ladder.record_result(challenge, self.player(5), self.player(5).user)
        self.assertEqual(self.ranked_usernames(), self.usernames_for(5, 1, 2, 3, 4, 6))


class LadderForfeitTests(LadderTestBase):
    def test_only_overdue_challenges_are_forfeited(self):
        self.allow_open_challenges(2)
        overdue = self.ladder.issue_challenge(self.player(4), self.player(3))
        upcoming = self.ladder.issue_challenge(self.player(6), self.player(5))
        self.make_overdue(overdue)

        self.ladder.resolve_overdue_challenges()

        overdue.refresh_from_db()
        upcoming.refresh_from_db()
        self.assertEqual(overdue.status, LadderChallenge.ChallengeStatuses.FORFEITED)
        self.assertTrue(upcoming.is_pending())
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 4, 3, 5, 6))

    def test_overdue_challenges_resolve_in_deadline_order(self):
        self.allow_open_challenges(2)
        earlier = self.ladder.issue_challenge(self.player(4), self.player(3))
        later = self.ladder.issue_challenge(self.player(6), self.player(4))
        self.make_overdue(earlier, days_overdue=2)
        self.make_overdue(later, days_overdue=1)

        self.ladder.resolve_overdue_challenges()

        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 6, 4, 3, 5))
        self.assert_positions_contiguous()

    def test_resolving_twice_changes_nothing(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.make_overdue(challenge)
        self.ladder.resolve_overdue_challenges()
        self.ladder.resolve_overdue_challenges()
        self.assertEqual(LadderChallenge.objects.get(pk=challenge.pk).match.result.is_forfeit, True)
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 4, 3, 5, 6))

    def test_overdue_challenge_frees_slot_before_issuing(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.make_overdue(challenge)
        next_challenge = self.ladder.issue_challenge(self.player(3), self.player(2))
        self.assertTrue(next_challenge.is_pending())


class LadderWithdrawAndVoidTests(LadderTestBase):
    def test_challenger_can_withdraw(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.ladder.withdraw_challenge(challenge, self.player(4).user)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, LadderChallenge.ChallengeStatuses.WITHDRAWN)

    def test_defender_cannot_withdraw(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        with self.assertRaises(PermissionDenied):
            self.ladder.withdraw_challenge(challenge, self.player(3).user)

    def test_organizer_can_withdraw(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.ladder.withdraw_challenge(challenge, self.organizer.user)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, LadderChallenge.ChallengeStatuses.WITHDRAWN)

    def test_resolved_challenge_cannot_be_withdrawn(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.ladder.record_result(challenge, None, self.player(4).user)
        with self.assertRaisesMessage(LadderRuleViolation, 'already been resolved'):
            self.ladder.withdraw_challenge(challenge, self.player(4).user)

    def test_organizer_void_marks_result_voided_without_moving_players(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.ladder.record_result(challenge, self.player(4), self.player(4).user)

        self.ladder.void_challenge(challenge, self.organizer.user)

        challenge.refresh_from_db()
        self.assertEqual(challenge.status, LadderChallenge.ChallengeStatuses.VOIDED)
        self.assertTrue(challenge.match.result.is_voided())
        self.assertEqual(challenge.match.result.voided_by, self.organizer.user)
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 4, 3, 5, 6))

    def test_player_cannot_void(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        with self.assertRaises(PermissionDenied):
            self.ladder.void_challenge(challenge, self.player(4).user)

    def test_withdrawn_challenge_cannot_be_voided(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.ladder.withdraw_challenge(challenge, self.player(4).user)
        with self.assertRaisesMessage(LadderRuleViolation, 'already been withdrawn or voided'):
            self.ladder.void_challenge(challenge, self.organizer.user)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class LadderViewTests(LadderTestBase):
    def ladder_url(self, name, *args):
        return reverse(name, args=[self.playgroup.slug, self.ladder.pk, *args])

    def message_texts(self, response):
        return [str(message) for message in get_messages(response.wsgi_request)]

    def test_detail_requires_login(self):
        response = self.client.get(self.ladder_url('pmc-pg-ladder-detail'))
        self.assertEqual(response.status_code, 302)

    def test_detail_forbidden_for_non_members(self):
        outsider = User.objects.create_user(username='outsider')
        self.client.force_login(outsider)
        response = self.client.get(self.ladder_url('pmc-pg-ladder-detail'))
        self.assertEqual(response.status_code, 403)

    def test_detail_lists_standings_and_challenge_options(self):
        self.client.force_login(self.player(5).user)
        response = self.client.get(self.ladder_url('pmc-pg-ladder-detail'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [standing.entry.member for standing in response.context['standings']], self.players)
        self.assertEqual(
            [standing.rank for standing in response.context['challengeable_standings']], [2, 3, 4])
        self.assertContains(response, 'name="defender_id"', count=3)
        self.assertContains(response, "You're #5")

    def test_detail_resolves_overdue_challenges(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.make_overdue(challenge)
        self.client.force_login(self.player(1).user)
        self.client.get(self.ladder_url('pmc-pg-ladder-detail'))
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, LadderChallenge.ChallengeStatuses.FORFEITED)

    def test_staff_pages_forbidden_for_players(self):
        self.client.force_login(self.player(1).user)
        self.assertEqual(self.client.get(self.ladder_url('pmc-pg-ladder-manage')).status_code, 403)
        self.assertEqual(self.client.get(self.ladder_url('pmc-pg-ladder-edit')).status_code, 403)
        self.assertEqual(self.client.get(
            reverse('pmc-pg-ladder-new', args=[self.playgroup.slug])).status_code, 403)

    def test_manage_page_renders_for_organizer(self):
        self.ladder.issue_challenge(self.player(4), self.player(3))
        self.client.force_login(self.organizer.user)
        response = self.client.get(self.ladder_url('pmc-pg-ladder-manage') + '?tab=challenges')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Void</button>')

    def test_actions_require_post(self):
        self.client.force_login(self.player(1).user)
        response = self.client.get(self.ladder_url('pmc-pg-ladder-leave'))
        self.assertEqual(response.status_code, 405)

    def test_ladders_are_unavailable_for_global_playgroups(self):
        global_playgroup = Playgroup.objects.create(
            name='Global', slug='global', is_global=True)
        self.enable_ladders_for(global_playgroup)
        self.client.force_login(self.player(1).user)
        response = self.client.get(reverse('pmc-pg-ladders', args=[global_playgroup.slug]))
        self.assertEqual(response.status_code, 404)

    def test_ladder_from_another_playgroup_is_not_found(self):
        other_playgroup = Playgroup.objects.create(name='Other', slug='other')
        self.enable_ladders_for(other_playgroup)
        other_member = self.create_member('other-member', playgroup=other_playgroup)
        self.client.force_login(other_member.user)
        response = self.client.get(
            reverse('pmc-pg-ladder-detail', args=[other_playgroup.slug, self.ladder.pk]))
        self.assertEqual(response.status_code, 404)

    def test_join_adds_member_at_the_bottom(self):
        newcomer = self.create_member('newcomer')
        self.client.force_login(newcomer.user)
        response = self.client.post(self.ladder_url('pmc-pg-ladder-join'))
        self.assertRedirects(response, self.ladder_url('pmc-pg-ladder-detail'))
        self.assertEqual(self.ladder.get_rank_of(newcomer), 7)

    def test_htmx_leave_responds_with_htmx_redirect(self):
        self.client.force_login(self.player(2).user)
        response = self.client.post(
            self.ladder_url('pmc-pg-ladder-leave'), HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Redirect'], self.ladder_url('pmc-pg-ladder-detail'))
        self.assertIsNone(self.ladder.get_rank_of(self.player(2)))

    def test_issue_challenge_view(self):
        self.client.force_login(self.player(4).user)
        response = self.client.post(
            self.ladder_url('pmc-pg-ladder-challenge-new'), {'defender_id': self.player(3).pk})
        self.assertIn('Challenge issued to player3.', self.message_texts(response))
        self.assertEqual(self.ladder.get_open_challenges().count(), 1)

    def test_rejected_challenge_shows_reason_and_creates_nothing(self):
        self.client.force_login(self.player(6).user)
        response = self.client.post(
            self.ladder_url('pmc-pg-ladder-challenge-new'), {'defender_id': self.player(1).pk})
        self.assertIn('You can only challenge players up to 3 places above you.',
                      self.message_texts(response))
        self.assertFalse(self.ladder.challenges.exists())

    def test_record_result_view(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.client.force_login(self.player(3).user)
        result_url = self.ladder_url('pmc-pg-ladder-challenge-result', challenge.pk)

        self.assertEqual(self.client.get(result_url).status_code, 200)
        self.client.post(result_url, {'outcome': 'player_one'})

        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 5, 3, 4, 6))

    def test_record_result_view_forbidden_for_unrelated_players(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.client.force_login(self.player(1).user)
        response = self.client.get(
            self.ladder_url('pmc-pg-ladder-challenge-result', challenge.pk))
        self.assertEqual(response.status_code, 403)

    def test_create_ladder_with_defaults(self):
        self.client.force_login(self.organizer.user)
        response = self.client.post(reverse('pmc-pg-ladder-new', args=[self.playgroup.slug]), {
            'name': 'Second Ladder',
            'challenges_enabled': 'on',
            'challenge_range': 3,
            'open_challenge_limit': 1,
            'response_window_days': 7,
        })
        ladder = Ladder.objects.get(name='Second Ladder')
        self.assertRedirects(response, reverse(
            'pmc-pg-ladder-manage', args=[self.playgroup.slug, ladder.pk]))
        self.assertEqual(ladder.playgroup, self.playgroup)
        self.assertEqual(ladder.created_by, self.organizer.user)

    def test_create_ladder_rejects_duplicate_name(self):
        self.client.force_login(self.organizer.user)
        response = self.client.post(reverse('pmc-pg-ladder-new', args=[self.playgroup.slug]), {
            'name': 'main ladder',
            'challenge_range': 3,
            'open_challenge_limit': 1,
            'response_window_days': 7,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already has a ladder with that name')

    def test_organizer_adds_member_at_position(self):
        newcomer = self.create_member('newcomer')
        self.client.force_login(self.organizer.user)
        self.client.post(self.ladder_url('pmc-pg-ladder-member-add'),
                         {'member': newcomer.pk, 'position': 1})
        self.assertEqual(self.ladder.get_rank_of(newcomer), 1)

    def test_organizer_moves_member(self):
        self.client.force_login(self.organizer.user)
        self.client.post(
            self.ladder_url('pmc-pg-ladder-member-move', self.player(6).pk), {'position': 2})
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 6, 2, 3, 4, 5))

    def test_organizer_removes_member(self):
        self.client.force_login(self.organizer.user)
        self.client.post(self.ladder_url('pmc-pg-ladder-member-remove', self.player(1).pk))
        self.assertEqual(self.ranked_usernames(), self.usernames_for(2, 3, 4, 5, 6))

    def test_player_cannot_move_members(self):
        self.client.force_login(self.player(6).user)
        response = self.client.post(
            self.ladder_url('pmc-pg-ladder-member-move', self.player(6).pk), {'position': 1})
        self.assertEqual(response.status_code, 403)

    def test_disabling_challenges_voids_open_challenges(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.client.force_login(self.organizer.user)
        self.client.post(self.ladder_url('pmc-pg-ladder-edit'), {
            'name': 'Main Ladder',
            'challenge_range': 3,
            'open_challenge_limit': 1,
            'response_window_days': 7,
        })
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, LadderChallenge.ChallengeStatuses.VOIDED)
        self.make_overdue(challenge)
        self.ladder.resolve_overdue_challenges()
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 3, 4, 5, 6))

    def test_late_result_view_explains_the_forfeit(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.make_overdue(challenge)
        self.client.force_login(self.player(3).user)
        response = self.client.post(
            self.ladder_url('pmc-pg-ladder-challenge-result', challenge.pk), {'outcome': 'player_two'})
        self.assertIn('The response window has passed, so the challenger won by forfeit.',
                      self.message_texts(response))
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 5, 3, 4, 6))

    def test_challenging_a_member_of_another_playgroup_is_not_found(self):
        other_playgroup = Playgroup.objects.create(name='Other', slug='other')
        outsider = self.create_member('outsider', playgroup=other_playgroup)
        self.client.force_login(self.player(4).user)
        response = self.client.post(
            self.ladder_url('pmc-pg-ladder-challenge-new'), {'defender_id': outsider.pk})
        self.assertEqual(response.status_code, 404)

    def test_malformed_defender_is_not_found(self):
        self.client.force_login(self.player(4).user)
        response = self.client.post(
            self.ladder_url('pmc-pg-ladder-challenge-new'), {'defender_id': 'abc'})
        self.assertEqual(response.status_code, 404)

    def test_htmx_withdraw_responds_with_htmx_redirect(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.client.force_login(self.player(4).user)
        response = self.client.post(
            self.ladder_url('pmc-pg-ladder-challenge-withdraw', challenge.pk), HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Redirect'], self.ladder_url('pmc-pg-ladder-detail'))
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, LadderChallenge.ChallengeStatuses.WITHDRAWN)

    def test_player_cannot_void_via_view(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.client.force_login(self.player(4).user)
        response = self.client.post(
            self.ladder_url('pmc-pg-ladder-challenge-void', challenge.pk))
        self.assertEqual(response.status_code, 403)

    def test_organizer_voids_via_view(self):
        challenge = self.ladder.issue_challenge(self.player(4), self.player(3))
        self.client.force_login(self.organizer.user)
        response = self.client.post(
            self.ladder_url('pmc-pg-ladder-challenge-void', challenge.pk))
        self.assertRedirects(response, self.ladder_url('pmc-pg-ladder-manage') + '?tab=challenges')
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, LadderChallenge.ChallengeStatuses.VOIDED)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class LadderNavigationTests(LadderTestBase):
    def nav_names(self, user, playgroup):
        self.client.force_login(user)
        response = self.client.get(reverse('pmc-pg-detail', args=[playgroup.slug]))
        return [str(link['name']) for link in response.context['nav_links']]

    def test_ladders_link_shown_when_ladders_exist(self):
        self.assertIn('Play', self.nav_names(self.player(1).user, self.playgroup))

    def test_ladders_link_shown_to_staff_before_any_ladder_exists(self):
        playgroup = Playgroup.objects.create(name='Fresh', slug='fresh')
        self.enable_ladders_for(playgroup)
        organizer = self.create_member('fresh-organizer', playgroup=playgroup, is_staff=True)
        self.assertIn('Play', self.nav_names(organizer.user, playgroup))

    def test_ladders_link_hidden_from_players_when_no_ladders_exist(self):
        playgroup = Playgroup.objects.create(name='Fresh', slug='fresh')
        self.enable_ladders_for(playgroup)
        member = self.create_member('fresh-member', playgroup=playgroup)
        self.assertNotIn('Play', self.nav_names(member.user, playgroup))

    def test_ladders_hidden_from_non_members(self):
        outsider = User.objects.create_user(username='outsider')
        self.assertNotIn('Play', self.nav_names(outsider, self.playgroup))
        response = self.client.get(reverse('pmc-pg-detail', args=[self.playgroup.slug]))
        self.assertNotIn('ladders', response.context)

    def test_playgroup_page_lists_ladders_for_members(self):
        self.client.force_login(self.player(1).user)
        response = self.client.get(reverse('pmc-pg-detail', args=[self.playgroup.slug]))
        self.assertContains(response, 'Main Ladder')


class FeatureResolutionTests(TestCase):
    def setUp(self):
        self.playgroup = Playgroup.objects.create(name='Feature Group', slug='feature-group')
        self.feature = Feature.objects.create(key='preview-thing', name='Preview Thing')

    def set_global(self, is_enabled):
        self.feature.is_enabled = is_enabled
        self.feature.save()

    def override(self, is_enabled):
        PlaygroupFeature.objects.create(
            playgroup=self.playgroup, feature=self.feature, is_enabled=is_enabled)

    def test_ladders_feature_is_seeded_globally_disabled(self):
        ladders = Feature.objects.get(key=Feature.Keys.LADDERS)
        self.assertFalse(ladders.is_enabled)
        self.assertFalse(self.playgroup.has_feature(Feature.Keys.LADDERS))

    def test_unknown_feature_is_disabled(self):
        self.assertFalse(self.playgroup.has_feature('does-not-exist'))

    def test_global_flag_applies_without_override(self):
        self.assertFalse(self.playgroup.has_feature('preview-thing'))
        self.set_global(True)
        self.assertTrue(self.playgroup.has_feature('preview-thing'))

    def test_override_enables_a_globally_disabled_feature(self):
        self.override(True)
        self.assertTrue(self.playgroup.has_feature('preview-thing'))

    def test_override_disables_a_globally_enabled_feature(self):
        self.set_global(True)
        self.override(False)
        self.assertFalse(self.playgroup.has_feature('preview-thing'))

    def test_override_only_affects_its_playgroup(self):
        self.override(True)
        other_playgroup = Playgroup.objects.create(name='Other', slug='other')
        self.assertFalse(other_playgroup.has_feature('preview-thing'))


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class LadderFeatureGuardTests(LadderTestBase):
    def setUp(self):
        super().setUp()
        PlaygroupFeature.objects.filter(playgroup=self.playgroup).update(is_enabled=False)
        self.playgroup_url = reverse('pmc-pg-detail', args=[self.playgroup.slug])

    def ladder_url(self, name):
        return reverse(name, args=[self.playgroup.slug, self.ladder.pk])

    def test_pages_redirect_to_the_playgroup_when_disabled(self):
        self.client.force_login(self.organizer.user)
        for url in [
            reverse('pmc-pg-ladders', args=[self.playgroup.slug]),
            reverse('pmc-pg-ladder-new', args=[self.playgroup.slug]),
            self.ladder_url('pmc-pg-ladder-detail'),
            self.ladder_url('pmc-pg-ladder-manage'),
        ]:
            self.assertRedirects(self.client.get(url), self.playgroup_url)

    def test_actions_redirect_without_changing_anything_when_disabled(self):
        newcomer = self.create_member('newcomer')
        self.client.force_login(newcomer.user)
        response = self.client.post(self.ladder_url('pmc-pg-ladder-join'))
        self.assertRedirects(response, self.playgroup_url)
        self.assertIsNone(self.ladder.get_rank_of(newcomer))

    def test_htmx_actions_redirect_when_disabled(self):
        self.client.force_login(self.player(2).user)
        response = self.client.post(
            self.ladder_url('pmc-pg-ladder-leave'), HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Redirect'], self.playgroup_url)
        self.assertEqual(self.ladder.get_rank_of(self.player(2)), 2)

    def test_nav_and_playgroup_page_hide_ladders_when_disabled(self):
        self.client.force_login(self.organizer.user)
        response = self.client.get(self.playgroup_url)
        nav_names = [str(link['name']) for link in response.context['nav_links']]
        self.assertNotIn('Play', nav_names)
        self.assertNotIn('ladders', response.context)
        self.assertNotContains(response, 'Add Ladder')
        self.assertNotIn('ladders', response.context['pg_features'])
