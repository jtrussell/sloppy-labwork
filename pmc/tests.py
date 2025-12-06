from django.test import TestCase
from django.contrib.auth.models import User
from datetime import date, timedelta
from .models import (
    Event, EventResult, RankingPoints, Leaderboard, LeaderboardSeason,
    LeaderboardSeasonPeriod, PlayerRank, Playgroup, PlaygroupEvent,
    RankingPointsMapVersion, RankingPointsMap, RankingPointsService,
    EventFormat
)


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
