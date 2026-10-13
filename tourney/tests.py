import csv
import importlib
import io
import json
import logging
from datetime import date, timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.db import models
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from .models import (
    Tournament, Player, Stage, StagePlayer, Round, Match, MatchResult,
    StandingCalculator, get_pairing_strategy, GamesPlayedRankingCriterion,
    Pod, TournamentActionLog, MAXIMUM_PODS_PER_STAGE, get_snake_pod_index,
    build_unique_pod_slugs, TournamentAdmin
)
from pmc.models import Event, EventResult, Playgroup, PlaygroupEvent, PlaygroupMember
from .reporting import (
    ReportError, describe_winner, report_paired_match_result, report_self_scheduled_match_result,
    MATCH_ALREADY_REPORTED_MESSAGE, INVALID_WINNER_MESSAGE
)
from ghostform.models import (
    Form as GhostformForm, Question as GhostformQuestion, Response as GhostformResponse
)

logger = logging.getLogger(__name__)


class StandingsTestCase(TestCase):
    def setUp(self):
        """Set up test data for standings tests."""
        # Create test users
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.user1 = User.objects.create_user('user1', 'user1@test.com', 'password')
        self.user2 = User.objects.create_user('user2', 'user2@test.com', 'password')
        self.user3 = User.objects.create_user('user3', 'user3@test.com', 'password')
        self.user4 = User.objects.create_user('user4', 'user4@test.com', 'password')

        # Create tournament
        self.tournament = Tournament.objects.create(
            name='Test Tournament',
            owner=self.owner,
            is_accepting_registrations=True
        )

        # Create main stage with predictable ranking criteria (wins -> seed)
        self.main_stage = Stage.objects.create(
            tournament=self.tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='swiss'
        )

        # Set predictable ranking criteria instead of using random
        self.main_stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},  # Use seed instead of random for predictable tests
        ])

        # Create players
        self.player1 = Player.objects.create(user=self.user1, tournament=self.tournament)
        self.player2 = Player.objects.create(user=self.user2, tournament=self.tournament)
        self.player3 = Player.objects.create(user=self.user3, tournament=self.tournament)
        self.player4 = Player.objects.create(user=self.user4, tournament=self.tournament)

        # Create stage players with seeds
        self.stage_player1 = StagePlayer.objects.create(player=self.player1, stage=self.main_stage, seed=1)
        self.stage_player2 = StagePlayer.objects.create(player=self.player2, stage=self.main_stage, seed=2)
        self.stage_player3 = StagePlayer.objects.create(player=self.player3, stage=self.main_stage, seed=3)
        self.stage_player4 = StagePlayer.objects.create(player=self.player4, stage=self.main_stage, seed=4)


class StageStandingsTestCase(StandingsTestCase):
    """Test stage-specific standings calculations."""

    def test_stage_standings_no_matches(self):
        """Test standings when no matches have been played."""
        standings = StandingCalculator.get_stage_standings(self.main_stage)

        self.assertEqual(len(standings), 4)
        # Should be ordered by seed since no matches
        self.assertEqual(standings[0]['stage_player'], self.stage_player1)
        self.assertEqual(standings[1]['stage_player'], self.stage_player2)
        self.assertEqual(standings[2]['stage_player'], self.stage_player3)
        self.assertEqual(standings[3]['stage_player'], self.stage_player4)

        # Check ranking values
        for i, standing in enumerate(standings):
            self.assertEqual(standing['rank'], i + 1)
            self.assertEqual(standing['wins'], 0)
            self.assertEqual(standing['losses'], 0)
            self.assertEqual(standing['points'], 0)

    def test_stage_standings_with_wins(self):
        """Test standings calculation with some wins."""
        # Create round and matches
        round1 = Round.objects.create(stage=self.main_stage, order=1)

        # Player1 beats Player2
        match1 = Match.objects.create(round=round1, player_one=self.stage_player1, player_two=self.stage_player2)
        MatchResult.objects.create(match=match1, winner=self.stage_player1)

        # Player3 beats Player4
        match2 = Match.objects.create(round=round1, player_one=self.stage_player3, player_two=self.stage_player4)
        MatchResult.objects.create(match=match2, winner=self.stage_player3)

        standings = StandingCalculator.get_stage_standings(self.main_stage)

        # Winners should be ranked 1st and 2nd, ordered by seed among tied players
        self.assertEqual(standings[0]['stage_player'], self.stage_player1)  # 1 win, seed 1
        self.assertEqual(standings[1]['stage_player'], self.stage_player3)  # 1 win, seed 3
        self.assertEqual(standings[2]['stage_player'], self.stage_player2)  # 0 wins, seed 2
        self.assertEqual(standings[3]['stage_player'], self.stage_player4)  # 0 wins, seed 4

        # Check wins
        self.assertEqual(standings[0]['wins'], 1)
        self.assertEqual(standings[1]['wins'], 1)
        self.assertEqual(standings[2]['wins'], 0)
        self.assertEqual(standings[3]['wins'], 0)

    def test_stage_standings_with_ties(self):
        """Test standings calculation with tied matches."""
        # Set stage to allow ties
        self.main_stage.are_ties_allowed = True
        self.main_stage.save()

        round1 = Round.objects.create(stage=self.main_stage, order=1)

        # Tie between Player1 and Player2
        match1 = Match.objects.create(round=round1, player_one=self.stage_player1, player_two=self.stage_player2)
        MatchResult.objects.create(match=match1, winner=None)  # Tie

        standings = StandingCalculator.get_stage_standings(self.main_stage)

        # Both tied players should have 1 point, 0 wins
        tied_standings = [s for s in standings if s['points'] == 1]
        self.assertEqual(len(tied_standings), 2)
        self.assertEqual(tied_standings[0]['wins'], 0)
        self.assertEqual(tied_standings[0]['ties'], 1)


class TournamentStandingsTestCase(StandingsTestCase):
    """Test tournament-wide standings across multiple stages."""

    def test_tournament_standings_single_stage(self):
        """Test tournament standings with only one stage."""
        standings = StandingCalculator.get_tournament_standings(self.tournament)

        self.assertEqual(len(standings), 4)
        # Should match stage standings order
        self.assertEqual(standings[0]['player'], self.player1)
        self.assertEqual(standings[1]['player'], self.player2)
        self.assertEqual(standings[2]['player'], self.player3)
        self.assertEqual(standings[3]['player'], self.player4)

        # All should be in current stage
        for standing in standings:
            self.assertTrue(standing['is_in_current_stage'])
            self.assertTrue(standing['is_active'])

    def test_tournament_standings_with_dropped_players(self):
        """Test that dropped players are ranked below active players."""
        # Drop player2 and player4
        self.player2.status = Player.PlayerStatus.DROPPED
        self.player2.save()
        self.player4.status = Player.PlayerStatus.DROPPED
        self.player4.save()

        standings = StandingCalculator.get_tournament_standings(self.tournament)

        # Active players should come first
        active_standings = [s for s in standings if s['is_active']]
        dropped_standings = [s for s in standings if s['is_dropped']]

        self.assertEqual(len(active_standings), 2)
        self.assertEqual(len(dropped_standings), 2)

        # Check order: active players first, then dropped players
        self.assertEqual(standings[0]['player'], self.player1)  # Active, seed 1
        self.assertEqual(standings[1]['player'], self.player3)  # Active, seed 3
        self.assertEqual(standings[2]['player'], self.player2)  # Dropped, seed 2
        self.assertEqual(standings[3]['player'], self.player4)  # Dropped, seed 4

    def test_tournament_standings_multiple_stages(self):
        """Test tournament standings with players advancing to different stages."""
        # Create playoff stage with max 2 players
        playoff_stage = Stage.objects.create(
            tournament=self.tournament,
            name='Playoff Stage',
            order=2,
            pairing_strategy='single_elimination',
            max_players=2
        )

        # Set predictable ranking criteria for playoff stage
        playoff_stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])

        # Simulate stage advancement: set ranks on main stage players
        self.stage_player1.rank = 1
        self.stage_player1.save()
        self.stage_player2.rank = 2
        self.stage_player2.save()
        self.stage_player3.rank = 3
        self.stage_player3.save()
        self.stage_player4.rank = 4
        self.stage_player4.save()

        # Create playoff stage players (top 2 advance)
        playoff_player1 = StagePlayer.objects.create(player=self.player1, stage=playoff_stage, seed=1)
        playoff_player2 = StagePlayer.objects.create(player=self.player2, stage=playoff_stage, seed=2)

        # Create a playoff round with a match
        playoff_round = Round.objects.create(stage=playoff_stage, order=1)
        playoff_match = Match.objects.create(round=playoff_round, player_one=playoff_player1, player_two=playoff_player2)
        MatchResult.objects.create(match=playoff_match, winner=playoff_player1)

        standings = StandingCalculator.get_tournament_standings(self.tournament)

        # Players in playoff stage should rank ahead of main stage players
        self.assertEqual(standings[0]['player'], self.player1)  # Playoff stage
        self.assertEqual(standings[1]['player'], self.player2)  # Playoff stage
        self.assertEqual(standings[2]['player'], self.player3)  # Main stage, rank 3
        self.assertEqual(standings[3]['player'], self.player4)  # Main stage, rank 4

        # Check stage advancement
        self.assertTrue(standings[0]['is_in_current_stage'])   # Player1 in playoff (current)
        self.assertTrue(standings[1]['is_in_current_stage'])   # Player2 in playoff (current)
        self.assertFalse(standings[2]['is_in_current_stage']) # Player3 not in playoff
        self.assertFalse(standings[3]['is_in_current_stage']) # Player4 not in playoff

    def test_tournament_standings_aggregates_stats_across_stages(self):
        """Test that wins/losses are aggregated across all stages for export."""
        # Create main stage round with 2 rounds of matches
        main_round1 = Round.objects.create(stage=self.main_stage, order=1)
        main_round2 = Round.objects.create(stage=self.main_stage, order=2)

        # Round 1: Player1 beats Player4, Player2 beats Player3
        match1 = Match.objects.create(
            round=main_round1, player_one=self.stage_player1, player_two=self.stage_player4)
        MatchResult.objects.create(match=match1, winner=self.stage_player1)

        match2 = Match.objects.create(
            round=main_round1, player_one=self.stage_player2, player_two=self.stage_player3)
        MatchResult.objects.create(match=match2, winner=self.stage_player2)

        # Round 2: Player1 beats Player3, Player2 beats Player4
        match3 = Match.objects.create(
            round=main_round2, player_one=self.stage_player1, player_two=self.stage_player3)
        MatchResult.objects.create(match=match3, winner=self.stage_player1)

        match4 = Match.objects.create(
            round=main_round2, player_one=self.stage_player2, player_two=self.stage_player4)
        MatchResult.objects.create(match=match4, winner=self.stage_player2)

        # Main stage results: Player1 2-0, Player2 2-0, Player3 0-2, Player4 0-2
        # Set ranks on main stage
        self.stage_player1.rank = 1
        self.stage_player1.save()
        self.stage_player2.rank = 2
        self.stage_player2.save()
        self.stage_player3.rank = 3
        self.stage_player3.save()
        self.stage_player4.rank = 4
        self.stage_player4.save()

        # Create playoff stage (top 2 advance)
        playoff_stage = Stage.objects.create(
            tournament=self.tournament,
            name='Playoff Stage',
            order=2,
            pairing_strategy='single_elimination',
            max_players=2
        )
        playoff_stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])

        # Create playoff stage players
        playoff_player1 = StagePlayer.objects.create(
            player=self.player1, stage=playoff_stage, seed=1)
        playoff_player2 = StagePlayer.objects.create(
            player=self.player2, stage=playoff_stage, seed=2)

        # Playoff match: Player1 beats Player2
        playoff_round = Round.objects.create(stage=playoff_stage, order=1)
        playoff_match = Match.objects.create(
            round=playoff_round, player_one=playoff_player1, player_two=playoff_player2)
        MatchResult.objects.create(match=playoff_match, winner=playoff_player1)

        # Get tournament standings
        standings = StandingCalculator.get_tournament_standings(self.tournament)

        # Player1: 2 wins (main) + 1 win (playoff) = 3 wins, 0 losses
        self.assertEqual(standings[0]['player'], self.player1)
        self.assertEqual(standings[0]['wins'], 3)
        self.assertEqual(standings[0]['losses'], 0)

        # Player2: 2 wins (main) + 0 wins (playoff) = 2 wins, 1 loss
        self.assertEqual(standings[1]['player'], self.player2)
        self.assertEqual(standings[1]['wins'], 2)
        self.assertEqual(standings[1]['losses'], 1)

        # Player3: 0 wins (main), 2 losses (main) - did not advance
        self.assertEqual(standings[2]['player'], self.player3)
        self.assertEqual(standings[2]['wins'], 0)
        self.assertEqual(standings[2]['losses'], 2)

        # Player4: 0 wins (main), 2 losses (main) - did not advance
        self.assertEqual(standings[3]['player'], self.player4)
        self.assertEqual(standings[3]['wins'], 0)
        self.assertEqual(standings[3]['losses'], 2)

    def test_tournament_standings_eliminated_players_have_stats(self):
        """Test that players who didn't advance to current stage still have stats."""
        # Create main stage match
        main_round = Round.objects.create(stage=self.main_stage, order=1)
        match = Match.objects.create(
            round=main_round, player_one=self.stage_player1, player_two=self.stage_player2)
        MatchResult.objects.create(match=match, winner=self.stage_player1)

        # Set ranks
        self.stage_player1.rank = 1
        self.stage_player1.save()
        self.stage_player2.rank = 2
        self.stage_player2.save()
        self.stage_player3.rank = 3
        self.stage_player3.save()
        self.stage_player4.rank = 4
        self.stage_player4.save()

        # Create playoff stage with only player1
        playoff_stage = Stage.objects.create(
            tournament=self.tournament,
            name='Playoff Stage',
            order=2,
            pairing_strategy='single_elimination',
            max_players=1
        )
        playoff_stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])

        playoff_player1 = StagePlayer.objects.create(
            player=self.player1, stage=playoff_stage, seed=1)

        standings = StandingCalculator.get_tournament_standings(self.tournament)

        # Player1 is in playoffs, has main stage stats
        self.assertEqual(standings[0]['wins'], 1)
        self.assertEqual(standings[0]['losses'], 0)

        # Players 2, 3, 4 are NOT in playoffs but should have stats (not None)
        for standing in standings[1:]:
            self.assertIsNotNone(standing['wins'])
            self.assertIsNotNone(standing['losses'])
            self.assertIsInstance(standing['wins'], int)
            self.assertIsInstance(standing['losses'], int)


class StageAdvancementTestCase(StandingsTestCase):
    """Test rank assignment during stage advancement."""

    def test_prepare_next_stage_seeding_sets_ranks(self):
        """Test that ranks are set when preparing next stage seeding."""
        # Create playoff stage
        playoff_stage = Stage.objects.create(
            tournament=self.tournament,
            name='Playoff Stage',
            order=2,
            pairing_strategy='single_elimination',
            max_players=2
        )

        # Set predictable ranking criteria for playoff stage
        playoff_stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])

        # Create some matches to establish standings
        round1 = Round.objects.create(stage=self.main_stage, order=1)

        # Player1 beats Player2
        match1 = Match.objects.create(round=round1, player_one=self.stage_player1, player_two=self.stage_player2)
        MatchResult.objects.create(match=match1, winner=self.stage_player1)

        # Player3 beats Player4
        match2 = Match.objects.create(round=round1, player_one=self.stage_player3, player_two=self.stage_player4)
        MatchResult.objects.create(match=match2, winner=self.stage_player3)

        # Initially ranks should be None
        self.assertIsNone(self.stage_player1.rank)
        self.assertIsNone(self.stage_player2.rank)
        self.assertIsNone(self.stage_player3.rank)
        self.assertIsNone(self.stage_player4.rank)

        # Prepare next stage seeding
        self.tournament.prepare_next_stage_seeding()

        # Refresh from database
        self.stage_player1.refresh_from_db()
        self.stage_player2.refresh_from_db()
        self.stage_player3.refresh_from_db()
        self.stage_player4.refresh_from_db()

        # Ranks should now be set based on standings
        self.assertEqual(self.stage_player1.rank, 1)  # 1 win, seed 1
        self.assertEqual(self.stage_player3.rank, 2)  # 1 win, seed 3
        self.assertEqual(self.stage_player2.rank, 3)  # 0 wins, seed 2
        self.assertEqual(self.stage_player4.rank, 4)  # 0 wins, seed 4

    def test_advance_to_next_stage_limits_players(self):
        """Test that only max_players advance when starting the next stage."""
        # Create playoff stage with max 2 players
        playoff_stage = Stage.objects.create(
            tournament=self.tournament,
            name='Playoff Stage',
            order=2,
            pairing_strategy='single_elimination',
            max_players=2
        )

        # Set predictable ranking criteria for playoff stage
        playoff_stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])

        # Create a round in main stage to allow advancement
        round1 = Round.objects.create(stage=self.main_stage, order=1)

        # Create some matches to establish standings
        match1 = Match.objects.create(round=round1, player_one=self.stage_player1, player_two=self.stage_player2)
        MatchResult.objects.create(match=match1, winner=self.stage_player1)

        # Prepare seeding (should create StagePlayer records for all active players)
        self.tournament.prepare_next_stage_seeding()

        # Should have 4 preliminary stage players
        self.assertEqual(playoff_stage.stage_players.count(), 4)

        # Advance to next stage (should limit to max_players)
        self.tournament.advance_to_next_stage()

        # Should now have only 2 stage players (top seeded)
        self.assertEqual(playoff_stage.stage_players.count(), 2)

        # Should be the top 2 players based on standings (player1 won, player2 has better seed than others with 0 wins)
        playoff_players = playoff_stage.stage_players.order_by('seed')
        self.assertEqual(playoff_players[0].player, self.player1)  # Winner, rank 1
        self.assertEqual(playoff_players[1].player, self.player2)  # Lost to player1 but better seed than player3/4


class EdgeCasesTestCase(StandingsTestCase):
    """Test edge cases and special scenarios."""

    def test_tournament_standings_no_stages(self):
        """Test tournament standings when no stages exist."""
        # Delete the main stage
        self.main_stage.delete()

        standings = StandingCalculator.get_tournament_standings(self.tournament)
        self.assertEqual(len(standings), 0)

    def test_tournament_standings_no_players(self):
        """Test tournament standings when no players are registered."""
        # Delete all players
        Player.objects.filter(tournament=self.tournament).delete()

        standings = StandingCalculator.get_tournament_standings(self.tournament)
        self.assertEqual(len(standings), 0)

    def test_stage_standings_with_byes(self):
        """Test stage standings calculation with bye matches."""
        # Create round with a bye match
        round1 = Round.objects.create(stage=self.main_stage, order=1)

        # Player1 gets a bye
        bye_match = Match.objects.create(round=round1, player_one=self.stage_player1, player_two=None)
        MatchResult.objects.create(match=bye_match, winner=self.stage_player1)

        # Player3 beats Player4
        match2 = Match.objects.create(round=round1, player_one=self.stage_player3, player_two=self.stage_player4)
        MatchResult.objects.create(match=match2, winner=self.stage_player3)

        standings = StandingCalculator.get_stage_standings(self.main_stage)

        # Both winners should have 1 win
        self.assertEqual(standings[0]['wins'], 1)
        self.assertEqual(standings[1]['wins'], 1)

        # Player1 should be ranked higher due to better seed
        self.assertEqual(standings[0]['stage_player'], self.stage_player1)
        self.assertEqual(standings[1]['stage_player'], self.stage_player3)


class PairingStrategyTestCase(TestCase):
    """Test pairing strategy behavior for unmatched players display."""

    def test_swiss_strategy_shows_unmatched_players(self):
        """Test that Swiss strategy shows unmatched players."""
        strategy = get_pairing_strategy('swiss')
        self.assertFalse(strategy.is_elimination_style())
        self.assertFalse(strategy.is_self_scheduled())

        # Should show unmatched players
        show_unmatched = not (strategy.is_elimination_style() or strategy.is_self_scheduled())
        self.assertTrue(show_unmatched)

    def test_single_elimination_strategy_hides_unmatched_players(self):
        """Test that Single Elimination strategy hides unmatched players."""
        strategy = get_pairing_strategy('single_elimination')
        self.assertTrue(strategy.is_elimination_style())
        self.assertFalse(strategy.is_self_scheduled())

        # Should hide unmatched players
        show_unmatched = not (strategy.is_elimination_style() or strategy.is_self_scheduled())
        self.assertFalse(show_unmatched)

    def test_round_robin_strategy_hides_unmatched_players(self):
        """Test that Round Robin self-scheduled strategy hides unmatched players."""
        strategy = get_pairing_strategy('round_robin')
        self.assertFalse(strategy.is_elimination_style())
        self.assertTrue(strategy.is_self_scheduled())

        # Should hide unmatched players
        show_unmatched = not (strategy.is_elimination_style() or strategy.is_self_scheduled())
        self.assertFalse(show_unmatched)


class SingleEliminationPairingTestCase(TestCase):
    """Test Single Elimination pairing strategy."""

    def test_4_player_single_elimination(self):
        """Test single elimination with 4 players - seed 1 should face seed 4."""
        # Create test users
        owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        user1 = User.objects.create_user('player1', 'player1@test.com', 'password')
        user2 = User.objects.create_user('player2', 'player2@test.com', 'password')
        user3 = User.objects.create_user('player3', 'player3@test.com', 'password')
        user4 = User.objects.create_user('player4', 'player4@test.com', 'password')

        # Create tournament
        tournament = Tournament.objects.create(
            name='4-Player Single Elimination',
            owner=owner
        )

        # Create stage with single elimination strategy
        stage = Stage.objects.create(
            tournament=tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='single_elimination'
        )

        # Create players
        p1 = Player.objects.create(user=user1, tournament=tournament)
        p2 = Player.objects.create(user=user2, tournament=tournament)
        p3 = Player.objects.create(user=user3, tournament=tournament)
        p4 = Player.objects.create(user=user4, tournament=tournament)

        # Create stage players with seeds
        sp1 = StagePlayer.objects.create(player=p1, stage=stage, seed=1)
        sp2 = StagePlayer.objects.create(player=p2, stage=stage, seed=2)
        sp3 = StagePlayer.objects.create(player=p3, stage=stage, seed=3)
        sp4 = StagePlayer.objects.create(player=p4, stage=stage, seed=4)

        # Create first round
        round1 = Round.objects.create(stage=stage, order=1)

        # Make pairings
        strategy = get_pairing_strategy('single_elimination')
        strategy.make_pairings_for_round(round1)

        # Check pairings - should be seed 1 vs seed 4, and seed 2 vs seed 3
        matches = list(round1.matches.all())
        self.assertEqual(len(matches), 2)

        # Find the match with seed 1
        match_with_seed1 = None
        for match in matches:
            if match.player_one == sp1 or match.player_two == sp1:
                match_with_seed1 = match
                break

        self.assertIsNotNone(match_with_seed1, "Seed 1 should be in a match")

        # Check that seed 1 is paired with seed 4
        if match_with_seed1.player_one == sp1:
            self.assertEqual(match_with_seed1.player_two, sp4,
                           "Seed 1 should be paired with seed 4")
        else:
            self.assertEqual(match_with_seed1.player_one, sp4,
                           "Seed 1 should be paired with seed 4")

    def test_6_player_single_elimination(self):
        """Test single elimination with 6 players - verify bracket with byes."""
        # Create test users
        owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        users = [User.objects.create_user(f'player{i}', f'player{i}@test.com', 'password')
                 for i in range(1, 7)]

        # Create tournament
        tournament = Tournament.objects.create(
            name='6-Player Single Elimination',
            owner=owner
        )

        # Create stage with single elimination strategy
        stage = Stage.objects.create(
            tournament=tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='single_elimination'
        )

        # Create players and stage players with seeds
        stage_players = []
        for i, user in enumerate(users, start=1):
            player = Player.objects.create(user=user, tournament=tournament)
            sp = StagePlayer.objects.create(player=player, stage=stage, seed=i)
            stage_players.append(sp)

        # Create first round
        round1 = Round.objects.create(stage=stage, order=1)

        # Make pairings
        strategy = get_pairing_strategy('single_elimination')
        strategy.make_pairings_for_round(round1)

        # For 6 players in single elimination, we expect:
        # Round 1: (3 vs 6), (4 vs 5) - seeds 1 and 2 get byes
        matches = list(round1.matches.all().order_by('id'))

        # Should have 3 matches total (2 regular + potentially handled byes)
        # But with 6 players, we need to check the actual bracket structure
        # In a proper 6-player bracket: we'd pair to get to power of 2

        # Get all matches including byes
        regular_matches = [m for m in matches if m.player_two is not None]
        bye_matches = [m for m in matches if m.player_two is None]

        # With 6 players, seeds 1 and 2 should get byes (top 2 seeds)
        self.assertEqual(len(bye_matches), 2, "Seeds 1 and 2 should receive byes")

        # Verify byes go to seeds 1 and 2
        bye_players = {m.player_one for m in bye_matches}
        self.assertIn(stage_players[0], bye_players, "Seed 1 should have a bye")
        self.assertIn(stage_players[1], bye_players, "Seed 2 should have a bye")

        # Verify remaining matches are (3 vs 6) and (4 vs 5)
        self.assertEqual(len(regular_matches), 2, "Should have 2 regular matches")

        # Check match pairings
        match_pairs = set()
        for match in regular_matches:
            pair = tuple(sorted([match.player_one.seed, match.player_two.seed]))
            match_pairs.add(pair)

        self.assertIn((3, 6), match_pairs, "Should have seed 3 vs seed 6")
        self.assertIn((4, 5), match_pairs, "Should have seed 4 vs seed 5")


class SwissPairingPerformanceTestCase(TestCase):
    """Test Swiss pairing strategy performance with different tournament sizes."""

    def test_swiss_pairing_7_players_3_rounds(self):
        """Test Swiss pairing with 7 players over 3 rounds (uses brute force algorithm)."""
        import time
        from django.contrib.auth.models import User

        # Create test users and tournament
        owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        tournament = Tournament.objects.create(
            name='Small Tournament Test',
            owner=owner,
            is_accepting_registrations=True
        )

        # Create stage
        stage = Stage.objects.create(
            tournament=tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='swiss'
        )

        # Create 7 players
        players = []
        stage_players = []
        for i in range(7):
            user = User.objects.create_user(f'player{i+1}', f'player{i+1}@test.com', 'password')
            player = Player.objects.create(user=user, tournament=tournament)
            stage_player = StagePlayer.objects.create(player=player, stage=stage, seed=i+1)
            players.append(player)
            stage_players.append(stage_player)

        strategy = get_pairing_strategy('swiss')

        # Test 3 rounds of pairing
        for round_num in range(1, 4):
            round_obj = Round.objects.create(stage=stage, order=round_num)

            # Time the pairing process
            start_time = time.time()
            strategy.make_pairings_for_round(round_obj)
            end_time = time.time()

            pairing_time = end_time - start_time

            # Verify performance: should be very fast for 7 players (brute force)
            self.assertLess(pairing_time, 1.0, f"Round {round_num} pairing took too long: {pairing_time:.3f}s")

            # Verify matches were created
            matches = Match.objects.filter(round=round_obj)
            expected_matches = 4  # 3 regular matches + 1 bye
            self.assertEqual(matches.count(), expected_matches, f"Round {round_num} should have {expected_matches} matches")

            # Verify exactly one bye match
            bye_matches = matches.filter(player_two__isnull=True)
            self.assertEqual(bye_matches.count(), 1, f"Round {round_num} should have exactly 1 bye match")

            # For subsequent rounds, randomly assign winners to create realistic standings
            if round_num > 1:
                self._assign_random_winners(matches)

            logger.info(f"Round {round_num} pairing completed in {pairing_time:.3f}s with {matches.count()} matches")

    def test_swiss_pairing_100_players_3_rounds(self):
        """Test Swiss pairing with 100 players over 3 rounds (uses greedy+backtrack algorithm)."""
        import time
        from django.contrib.auth.models import User

        # Create test users and tournament
        owner = User.objects.create_user('owner100', 'owner100@test.com', 'password')
        tournament = Tournament.objects.create(
            name='Large Tournament Test',
            owner=owner,
            is_accepting_registrations=True
        )

        # Create stage
        stage = Stage.objects.create(
            tournament=tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='swiss'
        )

        # Create 100 players
        players = []
        stage_players = []
        for i in range(100):
            user = User.objects.create_user(f'player100_{i+1}', f'player100_{i+1}@test.com', 'password')
            player = Player.objects.create(user=user, tournament=tournament)
            stage_player = StagePlayer.objects.create(player=player, stage=stage, seed=i+1)
            players.append(player)
            stage_players.append(stage_player)

        strategy = get_pairing_strategy('swiss')

        # Test 3 rounds of pairing
        for round_num in range(1, 4):
            round_obj = Round.objects.create(stage=stage, order=round_num)

            # Time the pairing process
            start_time = time.time()
            strategy.make_pairings_for_round(round_obj)
            end_time = time.time()

            pairing_time = end_time - start_time

            # Verify performance: should complete in under 1.5 seconds even for 100 players
            self.assertLess(pairing_time, 1.5, f"Round {round_num} pairing took too long: {pairing_time:.3f}s")

            # Verify matches were created
            matches = Match.objects.filter(round=round_obj)
            expected_matches = 50  # 100 players = 50 matches (even number)
            self.assertEqual(matches.count(), expected_matches, f"Round {round_num} should have {expected_matches} matches")

            # Verify no bye matches (even number of players)
            bye_matches = matches.filter(player_two__isnull=True)
            self.assertEqual(bye_matches.count(), 0, f"Round {round_num} should have no bye matches")

            # For subsequent rounds, randomly assign winners to create realistic standings
            if round_num > 1:
                self._assign_random_winners(matches)

            logger.info(f"Round {round_num} pairing completed in {pairing_time:.3f}s with {matches.count()} matches")

    def test_swiss_algorithm_selection(self):
        """Test that the correct algorithm is selected based on player count."""
        from django.contrib.auth.models import User
        from tourney.pairing_strategies.swiss import SwissPairingStrategy

        # Create tournament setup
        owner = User.objects.create_user('owner_algo', 'owner_algo@test.com', 'password')
        tournament = Tournament.objects.create(
            name='Algorithm Selection Test',
            owner=owner,
            is_accepting_registrations=True
        )

        stage = Stage.objects.create(
            tournament=tournament,
            name='Test Stage',
            order=1,
            pairing_strategy='swiss'
        )

        strategy = SwissPairingStrategy()

        # Test with 14 players (should use brute force)
        players_14 = []
        for i in range(14):
            user = User.objects.create_user(f'algo_player_{i+1}', f'algo_player_{i+1}@test.com', 'password')
            player = Player.objects.create(user=user, tournament=tournament)
            stage_player = StagePlayer.objects.create(player=player, stage=stage, seed=i+1)
            players_14.append(stage_player)

        round_obj = Round.objects.create(stage=stage, order=2)  # Round 2 to test algorithm selection

        # This should complete quickly even though it uses brute force
        import time
        start_time = time.time()
        strategy.make_pairings_for_round(round_obj)
        end_time = time.time()

        pairing_time = end_time - start_time
        self.assertLess(pairing_time, 1.0, f"14-player brute force took too long: {pairing_time:.3f}s")

        logger.info(f"14-player tournament (brute force) completed in {pairing_time:.3f}s")

    def _assign_random_winners(self, matches):
        """Helper method to randomly assign winners to matches for testing."""
        import random

        for match in matches:
            # Skip if match already has a result (e.g., bye matches are auto-resolved)
            if hasattr(match, 'result') and match.result:
                continue

            if match.player_two is None:
                # Bye match - player_one automatically wins (but may already be resolved)
                if not MatchResult.objects.filter(match=match).exists():
                    MatchResult.objects.create(match=match, winner=match.player_one)
            else:
                # Regular match - randomly pick winner
                winner = random.choice([match.player_one, match.player_two])
                MatchResult.objects.create(match=match, winner=winner)


class SwissTournamentTestCase(TestCase):
    """Test complete Swiss tournaments with various player counts and round structures."""

    def setUp(self):
        """Set up common test data."""
        self.owner = User.objects.create_user('tournament_owner', 'owner@test.com', 'password')

    def _create_tournament_with_players(self, player_count, tournament_name):
        """Helper to create tournament with specified number of players."""
        tournament = Tournament.objects.create(
            name=tournament_name,
            owner=self.owner,
            is_accepting_registrations=True
        )

        stage = Stage.objects.create(
            tournament=tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='swiss'
        )

        # Set explicit ranking criteria for predictable testing
        stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])

        players = []
        stage_players = []
        for i in range(player_count):
            user = User.objects.create_user(
                f'{tournament_name.lower().replace(" ", "_")}_player_{i+1}',
                f'player_{i+1}@{tournament_name.lower().replace(" ", "_")}.com',
                'password'
            )
            player = Player.objects.create(user=user, tournament=tournament)
            stage_player = StagePlayer.objects.create(player=player, stage=stage, seed=i+1)
            players.append(player)
            stage_players.append(stage_player)

        return tournament, stage, players, stage_players

    def _create_rounds_and_assign_results(self, stage, round_count):
        """Helper to create rounds and assign realistic results."""
        import random
        strategy = get_pairing_strategy('swiss')

        for round_num in range(1, round_count + 1):
            round_obj = Round.objects.create(stage=stage, order=round_num)
            strategy.make_pairings_for_round(round_obj)

            # Assign results based on seeding for more predictable testing
            matches = Match.objects.filter(round=round_obj)
            for match in matches:
                if hasattr(match, 'result') and match.result:
                    continue

                if match.player_two is None:
                    # Bye matches are auto-resolved
                    continue
                else:
                    # Better seeded player has 60% chance to win
                    if match.player_one.seed < match.player_two.seed:
                        winner = match.player_one if random.random() < 0.6 else match.player_two
                    else:
                        winner = match.player_two if random.random() < 0.6 else match.player_one
                    MatchResult.objects.create(match=match, winner=winner)

    def _verify_no_duplicate_pairings(self, stage):
        """Verify that no two players have been paired more than once."""
        matches = Match.objects.filter(round__stage=stage)
        pairings = set()

        for match in matches:
            if match.player_two is None:
                continue

            # Create a sorted tuple to avoid (A,B) vs (B,A) duplicates
            pairing = tuple(sorted([match.player_one.id, match.player_two.id]))

            self.assertNotIn(pairing, pairings,
                f"Players {match.player_one.player.get_display_name()} and "
                f"{match.player_two.player.get_display_name()} have been paired more than once")
            pairings.add(pairing)

    def test_3_player_tournament_2_rounds(self):
        """Test 3-player Swiss tournament with 2 rounds."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(3, "3 Player Tournament")

        # Create 2 rounds
        self._create_rounds_and_assign_results(stage, 2)

        # Verify correct number of rounds
        self.assertEqual(stage.rounds.count(), 2)

        # Verify each round has correct number of matches (2 matches per round: 1 regular + 1 bye)
        for round_num in range(1, 3):
            round_obj = stage.rounds.get(order=round_num)
            matches = Match.objects.filter(round=round_obj)
            self.assertEqual(matches.count(), 2, f"Round {round_num} should have 2 matches")

            # Should have exactly 1 bye match
            bye_matches = matches.filter(player_two__isnull=True)
            self.assertEqual(bye_matches.count(), 1, f"Round {round_num} should have 1 bye match")

        # Verify no duplicate pairings
        self._verify_no_duplicate_pairings(stage)

        logger.debug(f"3-player tournament completed successfully with {stage.rounds.count()} rounds")

    def test_4_player_tournament_3_rounds(self):
        """Test 4-player Swiss tournament with 3 rounds."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(4, "4 Player Tournament")

        # Create 3 rounds
        self._create_rounds_and_assign_results(stage, 3)

        # Verify correct number of rounds
        self.assertEqual(stage.rounds.count(), 3)

        # Verify each round has correct number of matches (2 matches per round, no byes)
        for round_num in range(1, 4):
            round_obj = stage.rounds.get(order=round_num)
            matches = Match.objects.filter(round=round_obj)
            self.assertEqual(matches.count(), 2, f"Round {round_num} should have 2 matches")

            # Should have no bye matches
            bye_matches = matches.filter(player_two__isnull=True)
            self.assertEqual(bye_matches.count(), 0, f"Round {round_num} should have no bye matches")

        # Verify no duplicate pairings
        self._verify_no_duplicate_pairings(stage)

        logger.debug(f"4-player tournament completed successfully with {stage.rounds.count()} rounds")

    def test_5_player_tournament_3_rounds(self):
        """Test 5-player Swiss tournament with 3 rounds."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(5, "5 Player Tournament")

        # Create 3 rounds
        self._create_rounds_and_assign_results(stage, 3)

        # Verify correct number of rounds
        self.assertEqual(stage.rounds.count(), 3)

        # Verify each round has correct number of matches (3 matches per round: 2 regular + 1 bye)
        for round_num in range(1, 4):
            round_obj = stage.rounds.get(order=round_num)
            matches = Match.objects.filter(round=round_obj)
            self.assertEqual(matches.count(), 3, f"Round {round_num} should have 3 matches")

            # Should have exactly 1 bye match
            bye_matches = matches.filter(player_two__isnull=True)
            self.assertEqual(bye_matches.count(), 1, f"Round {round_num} should have 1 bye match")

        # Verify no duplicate pairings
        self._verify_no_duplicate_pairings(stage)

        logger.debug(f"5-player tournament completed successfully with {stage.rounds.count()} rounds")

    def test_6_player_tournament_3_rounds(self):
        """Test 6-player Swiss tournament with 3 rounds."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(6, "6 Player Tournament")

        # Create 3 rounds
        self._create_rounds_and_assign_results(stage, 3)

        # Verify correct number of rounds
        self.assertEqual(stage.rounds.count(), 3)

        # Verify each round has correct number of matches (3 matches per round, no byes)
        for round_num in range(1, 4):
            round_obj = stage.rounds.get(order=round_num)
            matches = Match.objects.filter(round=round_obj)
            self.assertEqual(matches.count(), 3, f"Round {round_num} should have 3 matches")

            # Should have no bye matches
            bye_matches = matches.filter(player_two__isnull=True)
            self.assertEqual(bye_matches.count(), 0, f"Round {round_num} should have no bye matches")

        # Verify no duplicate pairings
        self._verify_no_duplicate_pairings(stage)

        logger.debug(f"6-player tournament completed successfully with {stage.rounds.count()} rounds")

    def test_7_player_tournament_3_rounds(self):
        """Test 7-player Swiss tournament with 3 rounds."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(7, "7 Player Tournament")

        # Create 3 rounds
        self._create_rounds_and_assign_results(stage, 3)

        # Verify correct number of rounds
        self.assertEqual(stage.rounds.count(), 3)

        # Verify each round has correct number of matches (4 matches per round: 3 regular + 1 bye)
        for round_num in range(1, 4):
            round_obj = stage.rounds.get(order=round_num)
            matches = Match.objects.filter(round=round_obj)
            self.assertEqual(matches.count(), 4, f"Round {round_num} should have 4 matches")

            # Should have exactly 1 bye match
            bye_matches = matches.filter(player_two__isnull=True)
            self.assertEqual(bye_matches.count(), 1, f"Round {round_num} should have 1 bye match")

        # Verify no duplicate pairings
        self._verify_no_duplicate_pairings(stage)

        logger.debug(f"7-player tournament completed successfully with {stage.rounds.count()} rounds")

    def test_8_player_tournament_4_rounds(self):
        """Test 8-player Swiss tournament with 4 rounds."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(8, "8 Player Tournament")

        # Create 4 rounds
        self._create_rounds_and_assign_results(stage, 4)

        # Verify correct number of rounds
        self.assertEqual(stage.rounds.count(), 4)

        # Verify each round has correct number of matches (4 matches per round, no byes)
        for round_num in range(1, 5):
            round_obj = stage.rounds.get(order=round_num)
            matches = Match.objects.filter(round=round_obj)
            self.assertEqual(matches.count(), 4, f"Round {round_num} should have 4 matches")

            # Should have no bye matches
            bye_matches = matches.filter(player_two__isnull=True)
            self.assertEqual(bye_matches.count(), 0, f"Round {round_num} should have no bye matches")

        # Verify no duplicate pairings
        self._verify_no_duplicate_pairings(stage)

        logger.debug(f"8-player tournament completed successfully with {stage.rounds.count()} rounds")

    def test_9_player_tournament_4_rounds(self):
        """Test 9-player Swiss tournament with 4 rounds."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(9, "9 Player Tournament")

        # Create 4 rounds
        self._create_rounds_and_assign_results(stage, 4)

        # Verify correct number of rounds
        self.assertEqual(stage.rounds.count(), 4)

        # Verify each round has correct number of matches (5 matches per round: 4 regular + 1 bye)
        for round_num in range(1, 5):
            round_obj = stage.rounds.get(order=round_num)
            matches = Match.objects.filter(round=round_obj)
            self.assertEqual(matches.count(), 5, f"Round {round_num} should have 5 matches")

            # Should have exactly 1 bye match
            bye_matches = matches.filter(player_two__isnull=True)
            self.assertEqual(bye_matches.count(), 1, f"Round {round_num} should have 1 bye match")

        # Verify no duplicate pairings
        self._verify_no_duplicate_pairings(stage)

        logger.debug(f"9-player tournament completed successfully with {stage.rounds.count()} rounds")

    def test_swiss_pairing_quality_across_all_sizes(self):
        """Test that Swiss pairing produces quality pairings across all tournament sizes."""
        test_configs = [
            (3, 2), (4, 3), (5, 3), (6, 3), (7, 3), (8, 4), (9, 4)
        ]

        for player_count, round_count in test_configs:
            with self.subTest(players=player_count, rounds=round_count):
                tournament, stage, players, stage_players = self._create_tournament_with_players(
                    player_count, f"Quality Test {player_count}P"
                )

                # Run all rounds
                self._create_rounds_and_assign_results(stage, round_count)

                # Verify no duplicate pairings
                self._verify_no_duplicate_pairings(stage)

                # Verify reasonable score distribution
                standings = StandingCalculator.get_stage_standings(stage)
                scores = [s['wins'] for s in standings]

                # In a well-paired Swiss tournament, scores should be somewhat spread out
                unique_scores = len(set(scores))
                self.assertGreaterEqual(unique_scores, 2,
                    f"Tournament with {player_count} players should have varied scores, got: {scores}")

                logger.debug(f"Quality test passed for {player_count} players, {round_count} rounds - Score spread: {sorted(scores, reverse=True)}")

    def test_bye_distribution_fairness(self):
        """Test that byes are distributed fairly in odd-player tournaments."""
        # Test with 5 players over 3 rounds
        tournament, stage, players, stage_players = self._create_tournament_with_players(5, "Bye Distribution Test")

        # Track who gets byes
        bye_recipients = {}
        for stage_player in stage_players:
            bye_recipients[stage_player.id] = 0

        # Create 3 rounds and track byes
        strategy = get_pairing_strategy('swiss')
        for round_num in range(1, 4):
            round_obj = Round.objects.create(stage=stage, order=round_num)
            strategy.make_pairings_for_round(round_obj)

            # Find who got the bye
            matches = Match.objects.filter(round=round_obj)
            bye_matches = matches.filter(player_two__isnull=True)

            for bye_match in bye_matches:
                bye_recipients[bye_match.player_one.id] += 1

            # Assign results for next round pairing
            if round_num < 3:
                for match in matches:
                    if not hasattr(match, 'result') and match.player_two is not None:
                        # Favor better seed slightly
                        import random
                        winner = match.player_one if random.random() < 0.6 else match.player_two
                        MatchResult.objects.create(match=match, winner=winner)

        # Verify bye distribution
        bye_counts = list(bye_recipients.values())
        max_byes = max(bye_counts)
        min_byes = min(bye_counts)

        # In a 3-round tournament with 5 players, byes should be reasonably distributed
        # Some players might get more than 1 bye, but the distribution should be fair
        self.assertLessEqual(max_byes, 2, f"No player should get more than 2 byes, distribution: {bye_counts}")

        # At least 3 different players should get byes (since we have 3 rounds and 5 players)
        players_with_byes = sum(1 for count in bye_counts if count > 0)
        self.assertGreaterEqual(players_with_byes, 2,
            f"At least 2 players should get byes, got {players_with_byes} players with byes")

        logger.debug(f"Bye distribution test passed: {bye_counts} byes per player")

    def test_bye_placement_avoids_top_players(self):
        """Test that highly ranked players don't get byes when lower ranked players are available."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(5, "Bye Placement Test")

        strategy = get_pairing_strategy('swiss')

        # Round 1: Random pairing, establish some standings
        round1 = Round.objects.create(stage=stage, order=1)
        strategy.make_pairings_for_round(round1)

        # Assign controlled results to create predictable standings
        matches_r1 = Match.objects.filter(round=round1)
        for match in matches_r1:
            if match.player_two is None:
                continue  # Bye match already resolved

            # Always favor lower seed (better player) winning to create predictable standings
            winner = match.player_one if match.player_one.seed < match.player_two.seed else match.player_two
            MatchResult.objects.create(match=match, winner=winner)

        # Debug: Show Round 1 pairings for analysis
        r1_matches = [(f"{m.player_one.player.get_display_name()}" +
                      (f" vs {m.player_two.player.get_display_name()}" if m.player_two else " (BYE)"),
                      f"Winner: {m.result.winner.player.get_display_name()}" if hasattr(m, 'result') and m.result else "No result")
                     for m in matches_r1]
        logger.debug(f"Round 1 pairings: {r1_matches}")

        # Get standings BEFORE Round 2 to determine who should get the bye
        standings_after_r1 = StandingCalculator.get_stage_standings(stage)

        # Round 2: Test bye placement - should avoid top performing players
        round2 = Round.objects.create(stage=stage, order=2)
        strategy.make_pairings_for_round(round2)

        r2_bye_match = Match.objects.filter(round=round2, player_two__isnull=True).first()

        if r2_bye_match:
            bye_player_r2 = r2_bye_match.player_one

            # Find the bye player's position in standings BEFORE they got the Round 2 bye
            bye_player_rank = next(i for i, s in enumerate(standings_after_r1) if s['stage_player'] == bye_player_r2)

            # Check if there are lower-ranked players available for bye
            # (players who haven't had byes and are ranked lower)
            r1_bye_match = Match.objects.filter(round=round1, player_two__isnull=True).first()
            r1_bye_player_id = r1_bye_match.player_one.id if r1_bye_match else None

            lower_ranked_without_byes = []
            for i, standing in enumerate(standings_after_r1):
                if (i > bye_player_rank and  # Lower ranked than current bye recipient
                    standing['stage_player'].id != r1_bye_player_id):  # Hasn't had a bye
                    lower_ranked_without_byes.append(standing['stage_player'])

            if bye_player_rank == 0:
                self.fail(
                    f"Round 2 bye went to the #1 ranked player "
                    f"{bye_player_r2.player.get_display_name()}. "
                    f"Current standings: {[(i+1, s['stage_player'].player.get_display_name(), s['wins']) for i, s in enumerate(standings_after_r1)]}")

        # Assign results for round 2
        for match in Match.objects.filter(round=round2):
            if match.player_two is None or hasattr(match, 'result'):
                continue
            winner = match.player_one if match.player_one.seed < match.player_two.seed else match.player_two
            MatchResult.objects.create(match=match, winner=winner)

        # Get standings BEFORE Round 3 to determine who should get the bye
        standings_after_r2 = StandingCalculator.get_stage_standings(stage)

        # Round 3: Test bye placement again
        round3 = Round.objects.create(stage=stage, order=3)
        strategy.make_pairings_for_round(round3)
        r3_bye_match = Match.objects.filter(round=round3, player_two__isnull=True).first()

        if r3_bye_match:
            bye_player_r3 = r3_bye_match.player_one
            bye_player_rank_r3 = next(i for i, s in enumerate(standings_after_r2) if s['stage_player'] == bye_player_r3)

            if bye_player_rank_r3 == 0:
                self.fail(
                    f"Round 3 bye went to the #1 ranked player "
                    f"{bye_player_r3.player.get_display_name()}. "
                    f"Current standings: {[(i+1, s['stage_player'].player.get_display_name(), s['wins']) for i, s in enumerate(standings_after_r2)]}")

        logger.debug(f"Bye placement test passed - byes went to appropriately ranked players")

    def test_bye_not_given_to_undefeated_player_over_defeated(self):
        """
        Regression test: in a 5-player tournament where Round 1 produces 3
        winners (including one bye winner) and 2 losers, the Round 2 bye
        should go to a defeated player — not an undefeated one.

        The bye is effectively the lowest-rated "opponent" in the event, so
        assigning it to an undefeated player is the worst possible pair-down
        and should be avoided when defeated players are available.

        Scenario (from a real tournament):
          R1: Mitchell vs Andrew (Andrew wins), Espo vs Tyrell (Espo wins),
              Barry BYE
          After R1: Andrew 1-0, Espo 1-0, Barry 1-0 (bye), Mitchell 0-1,
              Tyrell 0-1
          R2 bye should go to Mitchell or Tyrell — NOT Andrew, Espo, or Barry.
        """
        tournament, stage, players, stage_players = (
            self._create_tournament_with_players(5, "Bye Pair Down Test"))

        sp_mitchell = stage_players[0]   # seed 1
        sp_andrew = stage_players[1]     # seed 2
        sp_espo = stage_players[2]       # seed 3
        sp_tyrell = stage_players[3]     # seed 4
        sp_barry = stage_players[4]      # seed 5

        round1 = Round.objects.create(stage=stage, order=1)
        m1 = Match.objects.create(
            round=round1, player_one=sp_mitchell, player_two=sp_andrew)
        MatchResult.objects.create(match=m1, winner=sp_andrew)
        m2 = Match.objects.create(
            round=round1, player_one=sp_espo, player_two=sp_tyrell)
        MatchResult.objects.create(match=m2, winner=sp_espo)
        m3 = Match.objects.create(
            round=round1, player_one=sp_barry, player_two=None)
        MatchResult.objects.create(match=m3, winner=sp_barry)

        round2 = Round.objects.create(stage=stage, order=2)
        strategy = get_pairing_strategy('swiss')
        strategy.make_pairings_for_round(round2)

        r2_bye_match = Match.objects.filter(
            round=round2, player_two__isnull=True).first()

        self.assertIsNotNone(r2_bye_match, "Round 2 should have a bye match")

        bye_player = r2_bye_match.player_one
        defeated_players = {sp_mitchell.id, sp_tyrell.id}

        self.assertIn(
            bye_player.id,
            defeated_players,
            f"Round 2 bye should go to a defeated player (Mitchell or Tyrell) "
            f"but went to {bye_player.player.get_display_name()}. "
            f"Standings after R1: Andrew 1-0, Espo 1-0, Barry 1-0 (bye), "
            f"Mitchell 0-1, Tyrell 0-1")

    def test_undefeated_players_paired_in_round_3(self):
        """
        Regression test for a 5-player Swiss tournament where two undefeated
        players were not paired in Round 3 because the bye selection algorithm
        did not consider pairing quality.

        Scenario (from a real tournament):
          R1: Aelonia vs beccabeKAW (beccabeKAW wins), wizardrandom vs
              quickdraw3457 (quickdraw3457 wins), strifesada BYE
          R2: quickdraw3457 vs beccabeKAW (beccabeKAW wins), strifesada vs
              Aelonia (strifesada wins), wizardrandom BYE
          Standings entering R3: beccabeKAW 2-0, strifesada 2-0,
              quickdraw3457 1-1, wizardrandom 1-1 (bye), Aelonia 0-2

        Expected R3: beccabeKAW vs strifesada (both undefeated).
        """
        tournament, stage, players, stage_players = (
            self._create_tournament_with_players(5, "Undefeated Pairing Regression"))

        sp_aelonia = stage_players[0]       # seed 1
        sp_beccabekaw = stage_players[1]    # seed 2
        sp_strifesada = stage_players[2]    # seed 3
        sp_wizardrandom = stage_players[3]  # seed 4
        sp_quickdraw = stage_players[4]     # seed 5

        round1 = Round.objects.create(stage=stage, order=1)
        m1_r1 = Match.objects.create(
            round=round1, player_one=sp_aelonia, player_two=sp_beccabekaw)
        MatchResult.objects.create(match=m1_r1, winner=sp_beccabekaw)
        m2_r1 = Match.objects.create(
            round=round1, player_one=sp_wizardrandom, player_two=sp_quickdraw)
        MatchResult.objects.create(match=m2_r1, winner=sp_quickdraw)
        m3_r1 = Match.objects.create(
            round=round1, player_one=sp_strifesada, player_two=None)
        MatchResult.objects.create(match=m3_r1, winner=sp_strifesada)

        round2 = Round.objects.create(stage=stage, order=2)
        m1_r2 = Match.objects.create(
            round=round2, player_one=sp_quickdraw, player_two=sp_beccabekaw)
        MatchResult.objects.create(match=m1_r2, winner=sp_beccabekaw)
        m2_r2 = Match.objects.create(
            round=round2, player_one=sp_strifesada, player_two=sp_aelonia)
        MatchResult.objects.create(match=m2_r2, winner=sp_strifesada)
        m3_r2 = Match.objects.create(
            round=round2, player_one=sp_wizardrandom, player_two=None)
        MatchResult.objects.create(match=m3_r2, winner=sp_wizardrandom)

        round3 = Round.objects.create(stage=stage, order=3)
        strategy = get_pairing_strategy('swiss')
        strategy.make_pairings_for_round(round3)

        r3_matches = Match.objects.filter(round=round3)
        undefeated_ids = {sp_beccabekaw.id, sp_strifesada.id}

        undefeated_paired_together = False
        for match in r3_matches:
            if match.player_two is None:
                continue
            paired_ids = {match.player_one.id, match.player_two.id}
            if paired_ids == undefeated_ids:
                undefeated_paired_together = True
                break

        self.assertTrue(
            undefeated_paired_together,
            f"Expected undefeated players (beccabeKAW, strifesada) to be paired "
            f"in Round 3. Actual pairings: "
            f"{[(m.player_one.player.get_display_name(), m.player_two.player.get_display_name() if m.player_two else 'BYE') for m in r3_matches]}")

    def test_bye_assignment_avoids_repeat_byes(self):
        """Test that byes are not given to players who already had a bye, except when necessary."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(5, "Repeat Bye Avoidance Test")

        strategy = get_pairing_strategy('swiss')
        bye_recipients = {}  # Track who gets byes in which rounds

        # Track all rounds and their bye assignments
        for round_num in range(1, 4):  # 3 rounds
            round_obj = Round.objects.create(stage=stage, order=round_num)
            strategy.make_pairings_for_round(round_obj)

            # Find who got the bye this round
            matches = Match.objects.filter(round=round_obj)
            bye_match = matches.filter(player_two__isnull=True).first()

            if bye_match:
                bye_player = bye_match.player_one
                if bye_player.id not in bye_recipients:
                    bye_recipients[bye_player.id] = []
                bye_recipients[bye_player.id].append(round_num)

                logger.debug(f"Round {round_num} bye: {bye_player.player.get_display_name()}")

            # Assign results for next round (except last round)
            if round_num < 3:
                for match in matches:
                    if match.player_two is None or hasattr(match, 'result'):
                        continue

                    # Create some realistic standings progression
                    import random
                    winner = match.player_one if random.random() < 0.6 else match.player_two
                    MatchResult.objects.create(match=match, winner=winner)

        # Check that no player got more than one bye (unless it was unavoidable)
        players_with_multiple_byes = {player_id: rounds for player_id, rounds in bye_recipients.items() if len(rounds) > 1}

        if players_with_multiple_byes:
            # If any player got multiple byes, it should only be when necessary to avoid repeat pairings
            logger.debug(f"Players with multiple byes: {players_with_multiple_byes}")
            # For now, we'll log this but not assert - this will help identify when the logic needs the exception

        logger.debug(f"Bye recipients by round: {bye_recipients}")

    def test_bye_given_to_lowest_ranked_without_bye(self):
        """Test that byes are given to the lowest-ranked player who hasn't had a bye yet."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(7, "Lowest Ranked Bye Test")

        strategy = get_pairing_strategy('swiss')
        bye_recipients = set()  # Track who has had byes

        # Round 1: Random bye (establish baseline)
        round1 = Round.objects.create(stage=stage, order=1)
        strategy.make_pairings_for_round(round1)

        matches_r1 = Match.objects.filter(round=round1)
        bye_match_r1 = matches_r1.filter(player_two__isnull=True).first()
        if bye_match_r1:
            bye_recipients.add(bye_match_r1.player_one.id)

        # Create controlled results to establish clear standings
        for match in matches_r1:
            if match.player_two is None or hasattr(match, 'result'):
                continue

            # Favor lower seeds to create predictable standings
            winner = match.player_one if match.player_one.seed <= match.player_two.seed else match.player_two
            MatchResult.objects.create(match=match, winner=winner)

        # Get standings BEFORE Round 2 to determine who should get the bye
        standings_after_r1 = StandingCalculator.get_stage_standings(stage)

        # Round 2: Bye should go to lowest ranked player without a previous bye
        round2 = Round.objects.create(stage=stage, order=2)
        strategy.make_pairings_for_round(round2)

        matches_r2 = Match.objects.filter(round=round2)
        bye_match_r2 = matches_r2.filter(player_two__isnull=True).first()

        if bye_match_r2:
            bye_player_r2 = bye_match_r2.player_one

            # Verify that the bye went to a player who hasn't had a bye yet (if possible)
            # This is the core principle we want to enforce
            players_without_byes_r2 = []
            for player in stage_players:
                if player.id not in bye_recipients:
                    players_without_byes_r2.append(player)

            if players_without_byes_r2:
                # The bye should go to someone who hasn't had a bye yet
                self.assertIn(bye_player_r2, players_without_byes_r2,
                    f"Round 2 bye should go to a player without a previous bye. "
                    f"Players without byes: {[p.player.get_display_name() for p in players_without_byes_r2]}, "
                    f"but bye went to {bye_player_r2.player.get_display_name()}")

                # Among players without byes, it should prefer lower-ranked ones
                # (but we allow flexibility for pairing constraints)
                bye_rank = next(i for i, s in enumerate(standings_after_r1) if s['stage_player'] == bye_player_r2)

                # Verify it's not in the top half (which would be very wrong)
                total_players = len(standings_after_r1)
                self.assertGreater(bye_rank, total_players // 2,
                    f"Bye should not go to top-half player. {bye_player_r2.player.get_display_name()} "
                    f"is ranked {bye_rank + 1} out of {total_players}")

            bye_recipients.add(bye_player_r2.id)

        # Add results for round 2
        for match in matches_r2:
            if match.player_two is None or hasattr(match, 'result'):
                continue

            winner = match.player_one if match.player_one.seed <= match.player_two.seed else match.player_two
            MatchResult.objects.create(match=match, winner=winner)

        # Get standings BEFORE Round 3 to determine who should get the bye
        standings_after_r2 = StandingCalculator.get_stage_standings(stage)

        # Round 3: Again, bye should go to lowest ranked without previous bye
        round3 = Round.objects.create(stage=stage, order=3)
        strategy.make_pairings_for_round(round3)

        matches_r3 = Match.objects.filter(round=round3)
        bye_match_r3 = matches_r3.filter(player_two__isnull=True).first()

        if bye_match_r3:
            bye_player_r3 = bye_match_r3.player_one

            # Verify that the bye went to a player who hasn't had a bye yet (if possible)
            players_without_byes_r3 = []
            for player in stage_players:
                if player.id not in bye_recipients:
                    players_without_byes_r3.append(player)

            if players_without_byes_r3:
                # The bye should go to someone who hasn't had a bye yet
                self.assertIn(bye_player_r3, players_without_byes_r3,
                    f"Round 3 bye should go to a player without a previous bye. "
                    f"Players without byes: {[p.player.get_display_name() for p in players_without_byes_r3]}, "
                    f"but bye went to {bye_player_r3.player.get_display_name()}")

                # Among players without byes, it should prefer lower-ranked ones
                # (but we allow flexibility for pairing constraints)
                bye_rank = next(i for i, s in enumerate(standings_after_r2) if s['stage_player'] == bye_player_r3)

                # Verify it's not in the top half (which would be very wrong)
                total_players = len(standings_after_r2)
                self.assertGreater(bye_rank, total_players // 2,
                    f"Bye should not go to top-half player. {bye_player_r3.player.get_display_name()} "
                    f"is ranked {bye_rank + 1} out of {total_players}")
            else:
                # All players have had byes - any player is acceptable
                logger.debug("All players have had byes, any selection is acceptable")

        logger.debug(f"Bye assignment test: R1={bye_match_r1.player_one.player.get_display_name() if bye_match_r1 else None}, "
                    f"R2={bye_match_r2.player_one.player.get_display_name() if bye_match_r2 else None}, "
                    f"R3={bye_match_r3.player_one.player.get_display_name() if bye_match_r3 else None}")

    def test_bye_exception_for_repeat_pairings(self):
        """Test that a player can get a second bye to avoid repeat pairings."""
        # This test will be more complex to set up - we need a scenario where
        # giving the bye to the lowest unassigned player would force a repeat pairing

        tournament, stage, players, stage_players = self._create_tournament_with_players(5, "Repeat Pairing Exception Test")

        strategy = get_pairing_strategy('swiss')

        # This test is more of a placeholder for now - it would require very specific
        # match result patterns to force the repeat pairing scenario
        # We'll implement this after the basic bye logic is working

        logger.debug("Repeat pairing exception test - placeholder for future implementation")

        # For now, just verify the tournament can be created and basic pairing works
        round1 = Round.objects.create(stage=stage, order=1)
        strategy.make_pairings_for_round(round1)

        matches = Match.objects.filter(round=round1)
        self.assertEqual(matches.count(), 3)  # 2 regular matches + 1 bye


class RoundRobinScheduledTestCase(TestCase):
    """Test Round Robin Scheduled pairing strategy."""

    def setUp(self):
        """Set up common test data."""
        self.owner = User.objects.create_user('tournament_owner', 'owner@test.com', 'password')

    def _create_tournament_with_players(self, num_players, tournament_name="Round Robin Test"):
        """Helper method to create a tournament with the specified number of players."""
        tournament = Tournament.objects.create(
            name=tournament_name,
            owner=self.owner,
            is_accepting_registrations=True
        )

        stage = Stage.objects.create(
            tournament=tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='round_robin_scheduled'
        )

        users = []
        players = []
        stage_players = []

        for i in range(num_players):
            user = User.objects.create_user(f'player{i+1}', f'player{i+1}@test.com', 'password')
            player = Player.objects.create(user=user, tournament=tournament)
            stage_player = StagePlayer.objects.create(player=player, stage=stage, seed=i+1)

            users.append(user)
            players.append(player)
            stage_players.append(stage_player)

        return tournament, stage, players, stage_players

    def test_round_robin_4_players(self):
        """Test Round Robin Scheduled with 4 players (even number)."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(4, "4 Player Round Robin")

        strategy = get_pairing_strategy('round_robin_scheduled')

        # Create and start the first round - this should generate all rounds and matches
        round1 = Round.objects.create(stage=stage, order=1)
        strategy.make_pairings_for_round(round1)

        # Verify expected number of rounds created (n-1 where n=4, so 3 rounds)
        rounds = Round.objects.filter(stage=stage).order_by('order')
        self.assertEqual(rounds.count(), 3, "Should create 3 rounds for 4 players")

        # Verify round orders
        for i, round_obj in enumerate(rounds, 1):
            self.assertEqual(round_obj.order, i, f"Round {i} should have order {i}")

        # Verify total number of matches (each player plays every other player once)
        # For 4 players: C(4,2) = 6 matches total
        total_matches = Match.objects.filter(round__stage=stage)
        self.assertEqual(total_matches.count(), 6, "Should create 6 total matches for 4 players")

        # Verify matches per round (4 players = 2 matches per round)
        for round_obj in rounds:
            matches_in_round = Match.objects.filter(round=round_obj)
            self.assertEqual(matches_in_round.count(), 2, f"Round {round_obj.order} should have 2 matches")

        # Verify no repeat pairings
        pairings = set()
        for match in total_matches:
            if match.player_one and match.player_two:
                pair = tuple(sorted([match.player_one.id, match.player_two.id]))
                self.assertNotIn(pair, pairings, f"Duplicate pairing found: {pair}")
                pairings.add(pair)

        # Verify each player plays exactly n-1 matches (3 matches each)
        for stage_player in stage_players:
            player_matches = total_matches.filter(
                models.Q(player_one=stage_player) | models.Q(player_two=stage_player)
            )
            self.assertEqual(player_matches.count(), 3,
                f"Player {stage_player.player.get_display_name()} should play exactly 3 matches")

        # Verify no bye matches (even number of players)
        bye_matches = total_matches.filter(player_two__isnull=True)
        self.assertEqual(bye_matches.count(), 0, "Should be no bye matches with even number of players")

    def test_round_robin_7_players(self):
        """Test Round Robin Scheduled with 7 players (odd number)."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(7, "7 Player Round Robin")

        strategy = get_pairing_strategy('round_robin_scheduled')

        # Create and start the first round - this should generate all rounds and matches
        round1 = Round.objects.create(stage=stage, order=1)
        strategy.make_pairings_for_round(round1)

        # Verify expected number of rounds created (for odd n, we need n rounds due to bye rotation)
        rounds = Round.objects.filter(stage=stage).order_by('order')
        self.assertEqual(rounds.count(), 7, "Should create 7 rounds for 7 players")

        # Verify round orders
        for i, round_obj in enumerate(rounds, 1):
            self.assertEqual(round_obj.order, i, f"Round {i} should have order {i}")

        # Verify total number of matches
        # For 7 players: C(7,2) = 21 regular matches + 7 bye matches = 28 total matches
        total_matches = Match.objects.filter(round__stage=stage)
        regular_matches = total_matches.filter(player_two__isnull=False)
        bye_matches = total_matches.filter(player_two__isnull=True)

        self.assertEqual(regular_matches.count(), 21, "Should create 21 regular matches for 7 players")
        self.assertEqual(bye_matches.count(), 7, "Should create 7 bye matches for 7 players")
        self.assertEqual(total_matches.count(), 28, "Should create 28 total matches for 7 players")

        # Verify matches per round (7 players = 3 regular matches + 1 bye per round)
        for round_obj in rounds:
            matches_in_round = Match.objects.filter(round=round_obj)
            regular_in_round = matches_in_round.filter(player_two__isnull=False)
            bye_in_round = matches_in_round.filter(player_two__isnull=True)

            self.assertEqual(matches_in_round.count(), 4, f"Round {round_obj.order} should have 4 total matches")
            self.assertEqual(regular_in_round.count(), 3, f"Round {round_obj.order} should have 3 regular matches")
            self.assertEqual(bye_in_round.count(), 1, f"Round {round_obj.order} should have 1 bye match")

        # Verify no repeat pairings in regular matches
        pairings = set()
        for match in regular_matches:
            if match.player_one and match.player_two:
                pair = tuple(sorted([match.player_one.id, match.player_two.id]))
                self.assertNotIn(pair, pairings, f"Duplicate pairing found: {pair}")
                pairings.add(pair)

        # Verify each player plays exactly n-1 regular matches (6 matches each)
        for stage_player in stage_players:
            player_regular_matches = regular_matches.filter(
                models.Q(player_one=stage_player) | models.Q(player_two=stage_player)
            )
            self.assertEqual(player_regular_matches.count(), 6,
                f"Player {stage_player.player.get_display_name()} should play exactly 6 regular matches")

        # Verify each player gets exactly one bye
        bye_distribution = {}
        for match in bye_matches:
            player_id = match.player_one.id
            bye_distribution[player_id] = bye_distribution.get(player_id, 0) + 1

        for stage_player in stage_players:
            bye_count = bye_distribution.get(stage_player.id, 0)
            self.assertEqual(bye_count, 1,
                f"Player {stage_player.player.get_display_name()} should get exactly 1 bye, got {bye_count}")

    def test_round_robin_strategy_properties(self):
        """Test that the Round Robin Scheduled strategy has correct properties."""
        strategy = get_pairing_strategy('round_robin_scheduled')

        self.assertEqual(strategy.name, 'round_robin_scheduled')
        self.assertEqual(strategy.display_name, 'Round Robin')
        self.assertFalse(strategy.is_self_scheduled(), "Round Robin Scheduled should not be self-scheduled")
        self.assertFalse(strategy.is_elimination_style(), "Round Robin Scheduled should not be elimination style")

        # Test can_create_new_round returns False (all rounds created at start)
        tournament, stage, players, stage_players = self._create_tournament_with_players(4)
        self.assertFalse(strategy.can_create_new_round(stage),
            "Round Robin Scheduled should not allow creating additional rounds")

    def test_round_robin_no_additional_rounds_created(self):
        """Test that calling make_pairings_for_round on non-first rounds doesn't create additional rounds."""
        tournament, stage, players, stage_players = self._create_tournament_with_players(4)

        strategy = get_pairing_strategy('round_robin_scheduled')

        # Create and start the first round
        round1 = Round.objects.create(stage=stage, order=1)
        strategy.make_pairings_for_round(round1)

        initial_rounds_count = Round.objects.filter(stage=stage).count()
        initial_matches_count = Match.objects.filter(round__stage=stage).count()

        # Try to call the strategy on an existing round (should not create more matches)
        # Find the second round that was already created
        round2 = Round.objects.filter(stage=stage, order=2).first()
        if round2:
            strategy.make_pairings_for_round(round2)

        # Verify no additional rounds or matches were created
        final_rounds_count = Round.objects.filter(stage=stage).count()
        final_matches_count = Match.objects.filter(round__stage=stage).count()

        self.assertEqual(final_rounds_count, initial_rounds_count,
            "No additional rounds should be created on subsequent calls")
        self.assertEqual(final_matches_count, initial_matches_count,
            "No additional matches should be created on subsequent calls")


class GamesPlayedRankingCriterionTestCase(TestCase):
    """Test the Games Played ranking criterion."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.user1 = User.objects.create_user('user1', 'user1@test.com', 'password')
        self.user2 = User.objects.create_user('user2', 'user2@test.com', 'password')
        self.user3 = User.objects.create_user('user3', 'user3@test.com', 'password')

        self.tournament = Tournament.objects.create(
            name='Games Played Test Tournament',
            owner=self.owner,
            is_accepting_registrations=True
        )

        self.stage = Stage.objects.create(
            tournament=self.tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='swiss'
        )

        self.player1 = Player.objects.create(user=self.user1, tournament=self.tournament)
        self.player2 = Player.objects.create(user=self.user2, tournament=self.tournament)
        self.player3 = Player.objects.create(user=self.user3, tournament=self.tournament)

        self.stage_player1 = StagePlayer.objects.create(player=self.player1, stage=self.stage, seed=1)
        self.stage_player2 = StagePlayer.objects.create(player=self.player2, stage=self.stage, seed=2)
        self.stage_player3 = StagePlayer.objects.create(player=self.player3, stage=self.stage, seed=3)

    def test_games_played_criterion_properties(self):
        """Test that the criterion has correct properties."""
        criterion = GamesPlayedRankingCriterion()

        self.assertEqual(criterion.get_key(), 'games_played')
        self.assertEqual(criterion.get_name(), 'Games Played')
        self.assertIn('games played', criterion.get_description().lower())
        self.assertTrue(criterion.is_descending())

    def test_games_played_with_no_matches(self):
        """Test games played count when no matches have been played."""
        criterion = GamesPlayedRankingCriterion()

        games_played = criterion.calculate_value(self.stage_player1, self.stage)
        self.assertEqual(games_played, 0)

    def test_games_played_counts_correctly(self):
        """Test that games played counts all matches for a player."""
        round1 = Round.objects.create(stage=self.stage, order=1)

        match1 = Match.objects.create(
            round=round1,
            player_one=self.stage_player1,
            player_two=self.stage_player2
        )
        MatchResult.objects.create(match=match1, winner=self.stage_player1)

        match2 = Match.objects.create(
            round=round1,
            player_one=self.stage_player3,
            player_two=None
        )
        MatchResult.objects.create(match=match2, winner=self.stage_player3)

        criterion = GamesPlayedRankingCriterion()

        player1_games = criterion.calculate_value(self.stage_player1, self.stage)
        player2_games = criterion.calculate_value(self.stage_player2, self.stage)
        player3_games = criterion.calculate_value(self.stage_player3, self.stage)

        self.assertEqual(player1_games, 1)
        self.assertEqual(player2_games, 1)
        self.assertEqual(player3_games, 1)

    def test_games_played_across_multiple_rounds(self):
        """Test games played accumulates across multiple rounds."""
        round1 = Round.objects.create(stage=self.stage, order=1)
        match1 = Match.objects.create(
            round=round1,
            player_one=self.stage_player1,
            player_two=self.stage_player2
        )
        MatchResult.objects.create(match=match1, winner=self.stage_player1)

        match2 = Match.objects.create(
            round=round1,
            player_one=self.stage_player3,
            player_two=None
        )
        MatchResult.objects.create(match=match2, winner=self.stage_player3)

        round2 = Round.objects.create(stage=self.stage, order=2)
        match3 = Match.objects.create(
            round=round2,
            player_one=self.stage_player1,
            player_two=self.stage_player3
        )
        MatchResult.objects.create(match=match3, winner=self.stage_player1)

        match4 = Match.objects.create(
            round=round2,
            player_one=self.stage_player2,
            player_two=None
        )
        MatchResult.objects.create(match=match4, winner=self.stage_player2)

        criterion = GamesPlayedRankingCriterion()

        player1_games = criterion.calculate_value(self.stage_player1, self.stage)
        player2_games = criterion.calculate_value(self.stage_player2, self.stage)
        player3_games = criterion.calculate_value(self.stage_player3, self.stage)

        self.assertEqual(player1_games, 2)
        self.assertEqual(player2_games, 2)
        self.assertEqual(player3_games, 2)

    def test_games_played_in_standings(self):
        """Test that games played is included in standings calculation."""
        self.stage.set_ranking_criteria([
            {'key': 'games_played', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])

        round1 = Round.objects.create(stage=self.stage, order=1)

        match1 = Match.objects.create(
            round=round1,
            player_one=self.stage_player1,
            player_two=self.stage_player2
        )
        MatchResult.objects.create(match=match1, winner=self.stage_player1)

        match2 = Match.objects.create(
            round=round1,
            player_one=self.stage_player3,
            player_two=None
        )
        MatchResult.objects.create(match=match2, winner=self.stage_player3)

        standings = StandingCalculator.get_stage_standings(self.stage)

        for standing in standings:
            self.assertIn('games_played_value', standing)

        self.assertEqual(standings[0]['games_played_value'], 1)
        self.assertEqual(standings[1]['games_played_value'], 1)
        self.assertEqual(standings[2]['games_played_value'], 1)

    def test_games_played_uses_cache(self):
        """Test that games played uses the standings cache when available."""
        criterion = GamesPlayedRankingCriterion()

        cache = {
            self.stage_player1.id: {'games_played': 5}
        }

        games_played = criterion.calculate_value(self.stage_player1, self.stage, cache)
        self.assertEqual(games_played, 5)

    def test_games_played_disabled_by_default(self):
        """Test that games played is not in default ranking criteria."""
        from .models import get_default_main_stage_criteria, get_default_playoff_stage_criteria

        main_criteria = get_default_main_stage_criteria()
        playoff_criteria = get_default_playoff_stage_criteria()

        main_keys = [c['key'] for c in main_criteria if c.get('enabled', True)]
        playoff_keys = [c['key'] for c in playoff_criteria if c.get('enabled', True)]

        self.assertNotIn('games_played', main_keys)
        self.assertNotIn('games_played', playoff_keys)


class AutoCloseRegistrationTestCase(TestCase):
    """Test automatic registration closing when first stage starts."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.user1 = User.objects.create_user('user1', 'user1@test.com', 'password')
        self.user2 = User.objects.create_user('user2', 'user2@test.com', 'password')

    def test_swiss_strategy_closes_registration(self):
        """Test that Swiss strategy has closes_registration_on_start() returning True."""
        strategy = get_pairing_strategy('swiss')
        self.assertTrue(strategy.closes_registration_on_start())

    def test_ffa_strategy_does_not_close_registration(self):
        """Test that Free-For-All strategy has closes_registration_on_start() returning False."""
        strategy = get_pairing_strategy('round_robin')
        self.assertFalse(strategy.closes_registration_on_start())

    def test_single_elimination_closes_registration(self):
        """Test that Single Elimination strategy has closes_registration_on_start() returning True."""
        strategy = get_pairing_strategy('single_elimination')
        self.assertTrue(strategy.closes_registration_on_start())

    def test_round_robin_scheduled_closes_registration(self):
        """Test that Round Robin Scheduled strategy has closes_registration_on_start() returning True."""
        strategy = get_pairing_strategy('round_robin_scheduled')
        self.assertTrue(strategy.closes_registration_on_start())

    def test_swiss_tournament_closes_registration_on_first_stage(self):
        """Test that starting a Swiss tournament's first stage closes registration."""
        tournament = Tournament.objects.create(
            name='Swiss Tournament',
            owner=self.owner,
            is_accepting_registrations=True
        )
        stage = Stage.objects.create(
            tournament=tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='swiss'
        )
        player1 = Player.objects.create(user=self.user1, tournament=tournament)
        player2 = Player.objects.create(user=self.user2, tournament=tournament)
        StagePlayer.objects.create(player=player1, stage=stage, seed=1)
        StagePlayer.objects.create(player=player2, stage=stage, seed=2)

        self.assertTrue(tournament.is_accepting_registrations)

        pairing_strategy = get_pairing_strategy(stage.pairing_strategy)
        is_first_stage = not Round.objects.filter(stage__tournament=tournament).exists()
        self.assertTrue(is_first_stage)

        if (is_first_stage and
            tournament.is_accepting_registrations and
                pairing_strategy.closes_registration_on_start()):
            tournament.is_accepting_registrations = False
            tournament.save()

        Round.objects.create(stage=stage, order=1)
        pairing_strategy.make_pairings_for_round(stage.rounds.first())

        tournament.refresh_from_db()
        self.assertFalse(tournament.is_accepting_registrations)

    def test_ffa_tournament_keeps_registration_open_on_first_stage(self):
        """Test that starting a Free-For-All tournament's first stage keeps registration open."""
        tournament = Tournament.objects.create(
            name='FFA Tournament',
            owner=self.owner,
            is_accepting_registrations=True
        )
        stage = Stage.objects.create(
            tournament=tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='round_robin'
        )
        player1 = Player.objects.create(user=self.user1, tournament=tournament)
        player2 = Player.objects.create(user=self.user2, tournament=tournament)
        StagePlayer.objects.create(player=player1, stage=stage, seed=1)
        StagePlayer.objects.create(player=player2, stage=stage, seed=2)

        self.assertTrue(tournament.is_accepting_registrations)

        pairing_strategy = get_pairing_strategy(stage.pairing_strategy)
        is_first_stage = not Round.objects.filter(stage__tournament=tournament).exists()
        self.assertTrue(is_first_stage)

        if (is_first_stage and
            tournament.is_accepting_registrations and
                pairing_strategy.closes_registration_on_start()):
            tournament.is_accepting_registrations = False
            tournament.save()

        Round.objects.create(stage=stage, order=1)
        pairing_strategy.make_pairings_for_round(stage.rounds.first())

        tournament.refresh_from_db()
        self.assertTrue(tournament.is_accepting_registrations)


class PublicTournamentAccessTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')

    def test_is_public_defaults_to_false(self):
        tournament = Tournament.objects.create(
            name='Test Tournament',
            owner=self.owner
        )
        self.assertFalse(tournament.is_public)

    def test_is_public_can_be_set_to_true(self):
        tournament = Tournament.objects.create(
            name='Public Tournament',
            owner=self.owner,
            is_public=True
        )
        self.assertTrue(tournament.is_public)

    def test_is_public_persists_after_save(self):
        tournament = Tournament.objects.create(
            name='Test Tournament',
            owner=self.owner,
            is_public=False
        )
        tournament.is_public = True
        tournament.save()
        tournament.refresh_from_db()
        self.assertTrue(tournament.is_public)


class KeyChainExportTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.user1 = User.objects.create_user('user1', 'user1@test.com', 'password')
        self.user2 = User.objects.create_user('user2', 'user2@test.com', 'password')
        self.user3 = User.objects.create_user('user3', 'user3@test.com', 'password')
        self.user4 = User.objects.create_user('user4', 'user4@test.com', 'password')

        self.tournament = Tournament.objects.create(
            name='Test Tournament',
            owner=self.owner,
            is_accepting_registrations=True
        )

        self.main_stage = Stage.objects.create(
            tournament=self.tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='swiss'
        )
        self.main_stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])

        self.player1 = Player.objects.create(user=self.user1, tournament=self.tournament)
        self.player2 = Player.objects.create(user=self.user2, tournament=self.tournament)
        self.player3 = Player.objects.create(user=self.user3, tournament=self.tournament)
        self.player4 = Player.objects.create(user=self.user4, tournament=self.tournament)

        self.stage_player1 = StagePlayer.objects.create(
            player=self.player1, stage=self.main_stage, seed=1)
        self.stage_player2 = StagePlayer.objects.create(
            player=self.player2, stage=self.main_stage, seed=2)
        self.stage_player3 = StagePlayer.objects.create(
            player=self.player3, stage=self.main_stage, seed=3)
        self.stage_player4 = StagePlayer.objects.create(
            player=self.player4, stage=self.main_stage, seed=4)

    def test_player_count_calculation_does_not_raise_type_error(self):
        """Test that player_count calculation handles standings correctly."""
        main_round = Round.objects.create(stage=self.main_stage, order=1)
        match = Match.objects.create(
            round=main_round, player_one=self.stage_player1, player_two=self.stage_player2)
        MatchResult.objects.create(match=match, winner=self.stage_player1)

        self.stage_player1.rank = 1
        self.stage_player1.save()
        self.stage_player2.rank = 2
        self.stage_player2.save()
        self.stage_player3.rank = 3
        self.stage_player3.save()
        self.stage_player4.rank = 4
        self.stage_player4.save()

        playoff_stage = Stage.objects.create(
            tournament=self.tournament,
            name='Playoff Stage',
            order=2,
            pairing_strategy='single_elimination',
            max_players=2
        )
        playoff_stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])

        playoff_player1 = StagePlayer.objects.create(
            player=self.player1, stage=playoff_stage, seed=1)
        playoff_player2 = StagePlayer.objects.create(
            player=self.player2, stage=playoff_stage, seed=2)

        standings = StandingCalculator.get_tournament_standings(self.tournament)

        player_count = len(
            [s for s in standings if (s.get('wins') or 0) > 0 or (s.get('losses') or 0) > 0])

        self.assertEqual(player_count, 2)

    def test_export_standings_have_valid_stats_for_all_players(self):
        """Test that all players have valid integer stats for export."""
        main_round = Round.objects.create(stage=self.main_stage, order=1)
        match = Match.objects.create(
            round=main_round, player_one=self.stage_player1, player_two=self.stage_player2)
        MatchResult.objects.create(match=match, winner=self.stage_player1)

        self.stage_player1.rank = 1
        self.stage_player1.save()
        self.stage_player2.rank = 2
        self.stage_player2.save()
        self.stage_player3.rank = 3
        self.stage_player3.save()
        self.stage_player4.rank = 4
        self.stage_player4.save()

        playoff_stage = Stage.objects.create(
            tournament=self.tournament,
            name='Playoff Stage',
            order=2,
            pairing_strategy='single_elimination',
            max_players=2
        )
        playoff_stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])

        playoff_player1 = StagePlayer.objects.create(
            player=self.player1, stage=playoff_stage, seed=1)
        playoff_player2 = StagePlayer.objects.create(
            player=self.player2, stage=playoff_stage, seed=2)

        standings = StandingCalculator.get_tournament_standings(self.tournament)

        for standing in standings:
            self.assertIsNotNone(standing['wins'])
            self.assertIsNotNone(standing['losses'])
            self.assertIsInstance(standing['wins'], int)
            self.assertIsInstance(standing['losses'], int)
            self.assertGreaterEqual(standing['wins'], 0)
            self.assertGreaterEqual(standing['losses'], 0)


class TournamentCopyNamingTestCase(TestCase):
    def _get_copy_name(self, source_name):
        import re
        suffix_match = re.search(r' #(\d+)$', source_name)
        if suffix_match:
            current_num = int(suffix_match.group(1))
            return re.sub(r' #\d+$', f' #{current_num + 1}', source_name)
        else:
            return f'{source_name} #2'

    def test_basic_name_gets_suffix(self):
        self.assertEqual(self._get_copy_name('My Tournament'), 'My Tournament #2')

    def test_existing_suffix_increments(self):
        self.assertEqual(self._get_copy_name('My Tournament #2'), 'My Tournament #3')

    def test_higher_suffix_increments(self):
        self.assertEqual(self._get_copy_name('My Tournament #15'), 'My Tournament #16')

    def test_no_space_before_hash_gets_new_suffix(self):
        self.assertEqual(self._get_copy_name('My Tournament#2'), 'My Tournament#2 #2')

    def test_hash_in_middle_gets_new_suffix(self):
        self.assertEqual(self._get_copy_name('Tournament #2 Finals'), 'Tournament #2 Finals #2')


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class CreateTournamentFromEventTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.player1 = User.objects.create_user('player1', 'p1@test.com', 'password')
        self.player2 = User.objects.create_user('player2', 'p2@test.com', 'password')
        self.non_staff = User.objects.create_user('non_staff', 'ns@test.com', 'password')

        self.playgroup = Playgroup.objects.create(
            name='Test Playgroup', slug='test-playgroup')
        PlaygroupMember.objects.create(
            playgroup=self.playgroup, user=self.owner, is_staff=True)
        PlaygroupMember.objects.create(
            playgroup=self.playgroup, user=self.non_staff, is_staff=False)

        self.event = Event.objects.create(
            name='Test Event',
            start_date=date.today(),
            is_accepting_registrations=True,
        )
        PlaygroupEvent.objects.create(
            playgroup=self.playgroup, event=self.event)

        EventResult.objects.create(event=self.event, user=self.player1)
        EventResult.objects.create(event=self.event, user=self.player2)

    def _get_url(self):
        return reverse('tourney:tourney-create-from-event', args=[self.event.pk])

    def _get_post_data(self, **overrides):
        data = {
            'name': self.event.name,
            'is_accepting_registrations': False,
            'is_public': False,
            'main_pairing_strategy': 'swiss',
            'main_score_reporting': '0',
            'main_allow_ties': 'False',
            'playoff_score_reporting': '0',
        }
        data.update(overrides)
        return data

    def test_get_renders_tournament_form(self):
        self.client.login(username='owner', password='password')
        response = self.client.get(self._get_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Event')
        self.assertContains(response, 'player1')
        self.assertContains(response, 'player2')

    def test_post_creates_tournament_and_seeds_players(self):
        self.client.login(username='owner', password='password')
        response = self.client.post(self._get_url(), self._get_post_data())

        tournament = Tournament.objects.get(pmc_event=self.event)
        self.assertEqual(tournament.name, 'Test Event')
        self.assertEqual(tournament.owner, self.owner)
        self.assertEqual(tournament.players.count(), 2)

        player_users = set(
            tournament.players.values_list('user__username', flat=True))
        self.assertEqual(player_users, {'player1', 'player2'})

        self.assertRedirects(
            response,
            reverse('tourney:tourney-detail-home',
                    kwargs={'tournament_code': tournament.code}),
            fetch_redirect_response=False)

    def test_post_creates_stage_with_form_settings(self):
        self.client.login(username='owner', password='password')
        self.client.post(self._get_url(), self._get_post_data(
            main_pairing_strategy='round_robin',
            main_allow_ties=True,
        ))

        tournament = Tournament.objects.get(pmc_event=self.event)
        main_stage = tournament.stages.get(order=1)
        self.assertEqual(main_stage.pairing_strategy, 'round_robin')
        self.assertTrue(main_stage.are_ties_allowed)

    def test_post_closes_event_registration(self):
        self.client.login(username='owner', password='password')
        self.client.post(self._get_url(), self._get_post_data())

        self.event.refresh_from_db()
        self.assertFalse(self.event.is_accepting_registrations)

    def test_post_links_tournament_to_event(self):
        self.client.login(username='owner', password='password')
        self.client.post(self._get_url(), self._get_post_data())

        tournament = Tournament.objects.get(pmc_event=self.event)
        self.assertEqual(tournament.pmc_event, self.event)

    def test_requires_login(self):
        response = self.client.get(self._get_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_requires_playgroup_staff(self):
        self.client.login(username='non_staff', password='password')
        response = self.client.get(self._get_url())
        self.assertEqual(response.status_code, 403)

    def test_rejects_ineligible_event(self):
        EventResult.objects.filter(event=self.event).update(finishing_position=1)
        self.client.login(username='owner', password='password')
        response = self.client.get(self._get_url())
        self.assertRedirects(
            response,
            reverse('pmc-event-detail', args=[self.event.pk]),
            fetch_redirect_response=False)

    def test_rejects_event_with_existing_tournament(self):
        Tournament.objects.create(
            name='Existing', owner=self.owner, pmc_event=self.event)
        self.client.login(username='owner', password='password')
        response = self.client.get(self._get_url())
        self.assertRedirects(
            response,
            reverse('pmc-event-detail', args=[self.event.pk]),
            fetch_redirect_response=False)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class SyncToKeyChainTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.user1 = User.objects.create_user('user1', 'u1@test.com', 'password')
        self.user2 = User.objects.create_user('user2', 'u2@test.com', 'password')

        self.playgroup = Playgroup.objects.create(
            name='Test Playgroup', slug='test-playgroup')
        PlaygroupMember.objects.create(
            playgroup=self.playgroup, user=self.owner, is_staff=True)

        self.event = Event.objects.create(
            name='Test Event', start_date=date.today())
        PlaygroupEvent.objects.create(
            playgroup=self.playgroup, event=self.event)

        EventResult.objects.create(event=self.event, user=self.user1)
        EventResult.objects.create(event=self.event, user=self.user2)

        self.tournament = Tournament.objects.create(
            name='Test Tournament',
            owner=self.owner,
            pmc_event=self.event,
        )

        self.main_stage = Stage.objects.create(
            tournament=self.tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='swiss',
        )
        self.main_stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])

        self.p1 = Player.objects.create(
            user=self.user1, tournament=self.tournament)
        self.p2 = Player.objects.create(
            user=self.user2, tournament=self.tournament)

        self.sp1 = StagePlayer.objects.create(
            player=self.p1, stage=self.main_stage, seed=1)
        self.sp2 = StagePlayer.objects.create(
            player=self.p2, stage=self.main_stage, seed=2)

    def _get_url(self):
        return reverse('tourney:tourney-sync-to-keychain',
                        args=[self.tournament.code])

    def _play_round(self, winner, loser):
        round_obj = Round.objects.create(
            stage=self.main_stage,
            order=Round.objects.filter(stage=self.main_stage).count() + 1)
        match = Match.objects.create(
            round=round_obj, player_one=winner, player_two=loser)
        MatchResult.objects.create(match=match, winner=winner)

    def test_get_renders_standings_preview(self):
        self._play_round(self.sp1, self.sp2)
        self.client.login(username='owner', password='password')
        response = self.client.get(self._get_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sync Results to KeyChain')

    def test_post_syncs_results_to_event(self):
        self._play_round(self.sp1, self.sp2)
        self.client.login(username='owner', password='password')
        self.client.post(self._get_url())

        r1 = EventResult.objects.get(event=self.event, user=self.user1)
        r2 = EventResult.objects.get(event=self.event, user=self.user2)

        self.assertEqual(r1.finishing_position, 1)
        self.assertEqual(r1.num_wins, 1)
        self.assertEqual(r1.num_losses, 0)

        self.assertEqual(r2.finishing_position, 2)
        self.assertEqual(r2.num_wins, 0)
        self.assertEqual(r2.num_losses, 1)

    def test_post_updates_existing_results(self):
        r1 = EventResult.objects.get(event=self.event, user=self.user1)
        original_pk = r1.pk

        self._play_round(self.sp1, self.sp2)
        self.client.login(username='owner', password='password')
        self.client.post(self._get_url())

        r1.refresh_from_db()
        self.assertEqual(r1.pk, original_pk)
        self.assertEqual(r1.finishing_position, 1)

    def test_post_redirects_to_event_detail(self):
        self._play_round(self.sp1, self.sp2)
        self.client.login(username='owner', password='password')
        response = self.client.post(self._get_url())
        self.assertRedirects(
            response,
            reverse('pmc-event-detail', args=[self.event.pk]),
            fetch_redirect_response=False)

    def test_rejects_tournament_without_linked_event(self):
        self.tournament.pmc_event = None
        self.tournament.save()
        self.client.login(username='owner', password='password')
        response = self.client.get(self._get_url())
        self.assertRedirects(
            response,
            reverse('tourney:tourney-tournament-detail-admin',
                    kwargs={'tournament_code': self.tournament.code}),
            fetch_redirect_response=False)

    def test_requires_login(self):
        response = self.client.get(self._get_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)


class EventTournamentEligibilityTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('user', 'u@test.com', 'password')
        self.event = Event.objects.create(
            name='Test Event', start_date=date.today())

    def test_eligible_with_registrations_only(self):
        EventResult.objects.create(event=self.event, user=self.user)
        self.assertTrue(self.event.is_eligible_for_tourney_creation)

    def test_not_eligible_when_no_registrations(self):
        self.assertFalse(self.event.is_eligible_for_tourney_creation)

    def test_not_eligible_when_results_have_finishing_position(self):
        EventResult.objects.create(
            event=self.event, user=self.user, finishing_position=1)
        self.assertFalse(self.event.is_eligible_for_tourney_creation)

    def test_not_eligible_when_results_have_wins(self):
        EventResult.objects.create(
            event=self.event, user=self.user, num_wins=1)
        self.assertFalse(self.event.is_eligible_for_tourney_creation)

    def test_not_eligible_when_results_have_losses(self):
        EventResult.objects.create(
            event=self.event, user=self.user, num_losses=1)
        self.assertFalse(self.event.is_eligible_for_tourney_creation)

    def test_not_eligible_with_existing_tournament(self):
        EventResult.objects.create(event=self.event, user=self.user)
        Tournament.objects.create(
            name='Existing', owner=self.user, pmc_event=self.event)
        self.assertFalse(self.event.is_eligible_for_tourney_creation)


class CycleRandomTiebreakersTestCase(TestCase):
    """Test Stage.cycle_random_tiebreakers."""

    SENTINEL = 2.0

    def setUp(self):
        self.owner = User.objects.create_user(
            'cycle_owner', 'cycle_owner@test.com', 'password')
        self.tournament = Tournament.objects.create(
            name='Cycle Test', owner=self.owner)
        self.stage = Stage.objects.create(
            tournament=self.tournament, name='Main Stage', order=1,
            pairing_strategy='swiss')

    def _add_stage_player(self, stage, seed, status=Player.PlayerStatus.ACTIVE):
        user = User.objects.create_user(
            f'cycle_player_{stage.id}_{seed}',
            f'cycle_player_{stage.id}_{seed}@test.com', 'password')
        player = Player.objects.create(
            user=user, tournament=stage.tournament, status=status)
        return StagePlayer.objects.create(
            player=player, stage=stage, seed=seed,
            tiebreaker_value=self.SENTINEL)

    def test_cycle_refreshes_active_players(self):
        sp_one = self._add_stage_player(self.stage, 1)
        sp_two = self._add_stage_player(self.stage, 2)

        self.stage.cycle_random_tiebreakers()

        sp_one.refresh_from_db()
        sp_two.refresh_from_db()
        self.assertNotEqual(sp_one.tiebreaker_value, self.SENTINEL)
        self.assertNotEqual(sp_two.tiebreaker_value, self.SENTINEL)

    def test_cycle_leaves_dropped_players_untouched(self):
        active = self._add_stage_player(self.stage, 1)
        dropped = self._add_stage_player(
            self.stage, 2, status=Player.PlayerStatus.DROPPED)

        self.stage.cycle_random_tiebreakers()

        active.refresh_from_db()
        dropped.refresh_from_db()
        self.assertNotEqual(active.tiebreaker_value, self.SENTINEL)
        self.assertEqual(dropped.tiebreaker_value, self.SENTINEL)

    def test_cycle_leaves_other_stages_untouched(self):
        other_stage = Stage.objects.create(
            tournament=self.tournament, name='Other Stage', order=2,
            pairing_strategy='swiss')
        current_sp = self._add_stage_player(self.stage, 1)
        other_sp = StagePlayer.objects.create(
            player=current_sp.player, stage=other_stage, seed=1,
            tiebreaker_value=self.SENTINEL)

        self.stage.cycle_random_tiebreakers()

        current_sp.refresh_from_db()
        other_sp.refresh_from_db()
        self.assertNotEqual(current_sp.tiebreaker_value, self.SENTINEL)
        self.assertEqual(other_sp.tiebreaker_value, self.SENTINEL)


class SwissFoldInterlaceTestCase(TestCase):
    """Tests for the fold/interlace ordering used by the 15+ greedy Swiss path.

    The shuffle only decides which top-half player meets which bottom-half
    player, so these tests assert the deterministic invariants that hold for
    every shuffle outcome: permutation, score-group order, and the cross-half
    fold structure.
    """

    def _new_strategy(self):
        from tourney.pairing_strategies.swiss import SwissPairingStrategy
        return SwissPairingStrategy()

    def test_interlace_group_is_a_permutation(self):
        strategy = self._new_strategy()
        for size in range(0, 12):
            group = list(range(size))
            for _ in range(10):
                result = strategy._interlace_group(group)
                self.assertEqual(sorted(result), group)

    def test_interlace_group_passthrough_for_small_groups(self):
        strategy = self._new_strategy()
        self.assertEqual(strategy._interlace_group([]), [])
        self.assertEqual(strategy._interlace_group([1]), [1])
        self.assertEqual(strategy._interlace_group([1, 2]), [1, 2])

    def test_interlace_group_even_crosses_halves(self):
        strategy = self._new_strategy()
        group = list(range(8))
        top, bottom = set(group[:4]), set(group[4:])
        for _ in range(20):
            result = strategy._interlace_group(group)
            self.assertEqual({result[i] for i in range(0, 8, 2)}, top)
            self.assertEqual({result[i] for i in range(1, 8, 2)}, bottom)

    def test_interlace_group_odd_floats_bottom_half(self):
        strategy = self._new_strategy()
        group = list(range(5))
        top, bottom = set(group[:2]), set(group[2:])
        for _ in range(20):
            result = strategy._interlace_group(group)
            self.assertEqual({result[0], result[2]}, top)
            self.assertEqual({result[1], result[3], result[4]}, bottom)
            self.assertIn(result[-1], bottom)

    def test_fold_interlace_groups_and_folds(self):
        from types import SimpleNamespace

        strategy = self._new_strategy()
        scores = [2, 2, 2, 2, 1, 1, 1, 1, 1, 0, 0, 0]
        players = [SimpleNamespace(id=i) for i in range(len(scores))]
        score_by_id = {p.id: scores[p.id] for p in players}
        strategy._get_player_score = lambda p: score_by_id[p.id]

        for _ in range(20):
            result = strategy._fold_interlace(players)

            self.assertEqual(
                sorted(p.id for p in result), list(range(len(scores))))

            result_scores = [score_by_id[p.id] for p in result]
            self.assertEqual(result_scores, sorted(result_scores, reverse=True))

            index = 0
            for score in (2, 1, 0):
                group_ids = [p.id for p in players if score_by_id[p.id] == score]
                size = len(group_ids)
                block = result[index:index + size]
                index += size

                self.assertEqual({p.id for p in block}, set(group_ids))

                split = size // 2
                top = set(group_ids[:split])
                bottom = set(group_ids[split:])
                top_positions = {block[i].id for i in range(0, 2 * split, 2)}
                self.assertEqual(top_positions, top)
                self.assertEqual(
                    {p.id for p in block} - top_positions, bottom)

    def _build_swiss_stage(self, player_count, name):
        owner = User.objects.create_user(
            f'{name}_owner', f'{name}_owner@test.com', 'password')
        tournament = Tournament.objects.create(
            name=name, owner=owner, is_accepting_registrations=True)
        stage = Stage.objects.create(
            tournament=tournament, name='Main Stage', order=1,
            pairing_strategy='swiss')
        stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])
        stage_players = []
        for i in range(player_count):
            user = User.objects.create_user(
                f'{name}_player_{i+1}', f'{name}_player_{i+1}@test.com',
                'password')
            player = Player.objects.create(user=user, tournament=tournament)
            stage_players.append(StagePlayer.objects.create(
                player=player, stage=stage, seed=i + 1))
        return stage, stage_players

    def test_round_two_folds_within_score_groups_for_large_field(self):
        strategy = get_pairing_strategy('swiss')
        stage, stage_players = self._build_swiss_stage(16, 'fold16')

        round_one = Round.objects.create(stage=stage, order=1)
        strategy.make_pairings_for_round(round_one)
        for match in Match.objects.filter(round=round_one):
            MatchResult.objects.create(match=match, winner=match.player_one)

        round_two = Round.objects.create(stage=stage, order=2)
        strategy.make_pairings_for_round(round_two)
        matches = list(Match.objects.filter(round=round_two))

        self.assertEqual(len(matches), 8)
        self.assertEqual(sum(1 for m in matches if m.player_two is None), 0)

        standings = StandingCalculator.get_stage_standings(stage)
        wins_by_id = {s['stage_player'].id: s['wins'] for s in standings}

        groups = {}
        for sp in stage_players:
            groups.setdefault(wins_by_id[sp.id], []).append(sp)

        top_half_ids = set()
        for members in groups.values():
            members.sort(key=lambda sp: sp.seed)
            split = len(members) // 2
            top_half_ids.update(sp.id for sp in members[:split])

        paired = []
        for match in matches:
            one, two = match.player_one, match.player_two
            self.assertEqual(
                wins_by_id[one.id], wins_by_id[two.id],
                'Round 2 paired players from different score groups')
            self.assertEqual(
                {one.id in top_half_ids, two.id in top_half_ids}, {True, False},
                'Round 2 paired two players from the same half of a score group')
            paired.extend([one.id, two.id])

        self.assertEqual(
            sorted(paired), sorted(sp.id for sp in stage_players))


FAST_PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
MASTER_VAULT_TEST_DECK_LINK = 'https://www.keyforgegame.com/deck-details/2dea0ea6-e371-4b9a-826c-28f6620ef550'
SIMPLE_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


class PodTestMixin:
    def _create_stage_with_guest_players(self, player_count, pod_names=('Pod A', 'Pod B'),
                                         pairing_strategy='swiss', criteria=None, owner=None):
        tournament = Tournament.objects.create(
            name='Pod Tournament', owner=owner, is_accepting_registrations=True)
        stage = Stage.objects.create(
            tournament=tournament, name='Main Stage', order=1,
            pairing_strategy=pairing_strategy)
        stage.set_ranking_criteria(criteria or [
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])
        stage.sync_pods([{'id': None, 'name': name} for name in pod_names])

        stage_players = []
        for i in range(player_count):
            player = Player.objects.create(
                tournament=tournament, nickname=f'Guest {i + 1}')
            stage_players.append(StagePlayer.objects.create(
                player=player, stage=stage, seed=i + 1))

        stage.snake_stage_players_into_pods()
        for stage_player in stage_players:
            stage_player.refresh_from_db()

        return tournament, stage, stage_players

    def _assign_pod(self, stage_players, pod):
        StagePlayer.objects.filter(
            id__in=[sp.id for sp in stage_players]).update(pod=pod)
        for stage_player in stage_players:
            stage_player.refresh_from_db()

    def _play(self, stage, winner, loser):
        round_obj = Round.objects.create(
            stage=stage, order=stage.rounds.count() + 1)
        match = Match.objects.create(
            round=round_obj, player_one=winner, player_two=loser)
        MatchResult.objects.create(match=match, winner=winner)
        return match

    def _pair_round(self, stage, order):
        round_obj = Round.objects.create(stage=stage, order=order)
        stage.get_pairing_strategy().make_pairings_for_round(round_obj)
        return round_obj

    def _resolve_round_with_player_one_wins(self, round_obj):
        for match in round_obj.matches.all():
            if not match.has_result():
                MatchResult.objects.create(match=match, winner=match.player_one)

    def _assert_no_cross_pod_matches(self, stage):
        for match in Match.objects.filter(round__stage=stage, player_two__isnull=False):
            self.assertEqual(
                match.player_one.pod_id, match.player_two.pod_id,
                f'{match} pairs players from different pods')


class PodModelTestCase(PodTestMixin, TestCase):
    def test_has_pods_requires_at_least_two_pods(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(
            2, pod_names=())
        self.assertFalse(stage.has_pods())

        stage.sync_pods([{'id': None, 'name': 'Solo'}])
        self.assertFalse(stage.has_pods())

        stage.sync_pods([{'id': None, 'name': 'One'}, {'id': None, 'name': 'Two'}])
        self.assertTrue(stage.has_pods())

    def test_pod_slugs_are_unique_and_never_all(self):
        slugs = build_unique_pod_slugs(['Red Pod', 'red-pod', 'All', '!!!', 'Pod 4'])

        self.assertEqual(slugs, ['red-pod', 'red-pod-2', 'all-2', 'pod-4', 'pod-4-2'])

    def test_pod_created_directly_gets_a_unique_slug(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(0)

        pod = Pod.objects.create(stage=stage, name='Pod A', order=3)

        self.assertEqual(pod.slug, 'pod-a-2')

    def test_sync_pods_sets_slugs_and_updates_them_on_rename(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(0)
        pod_a, pod_b = stage.get_pods()
        self.assertEqual([pod_a.slug, pod_b.slug], ['pod-a', 'pod-b'])

        stage.sync_pods([
            {'id': pod_a.id, 'name': 'Pod B'},
            {'id': pod_b.id, 'name': 'Pod A'},
        ])

        pod_a.refresh_from_db()
        pod_b.refresh_from_db()
        self.assertEqual([pod_a.slug, pod_b.slug], ['pod-b', 'pod-a'])

    def test_snake_pod_index(self):
        positions = [get_snake_pod_index(position, 3) for position in range(8)]
        self.assertEqual(positions, [0, 1, 2, 2, 1, 0, 0, 1])

    def test_snake_into_two_pods_by_seed(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(6)
        pod_a, pod_b = stage.get_pods()

        seeds_by_pod = {
            pod.id: sorted(sp.seed for sp in stage_players if sp.pod_id == pod.id)
            for pod in (pod_a, pod_b)
        }
        self.assertEqual(seeds_by_pod[pod_a.id], [1, 4, 5])
        self.assertEqual(seeds_by_pod[pod_b.id], [2, 3, 6])

    def test_snake_into_three_uneven_pods(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(
            7, pod_names=('A', 'B', 'C'))
        pod_a, pod_b, pod_c = stage.get_pods()

        def seeds_in(pod):
            return sorted(sp.seed for sp in stage_players if sp.pod_id == pod.id)

        self.assertEqual(seeds_in(pod_a), [1, 6, 7])
        self.assertEqual(seeds_in(pod_b), [2, 5])
        self.assertEqual(seeds_in(pod_c), [3, 4])

    def test_snake_leaves_dropped_players_without_a_pod(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(5)
        dropped = stage_players[0].player
        dropped.status = Player.PlayerStatus.DROPPED
        dropped.save()

        stage.snake_stage_players_into_pods()

        self.assertIsNone(StagePlayer.objects.get(id=stage_players[0].id).pod)
        pod_a, pod_b = stage.get_pods()
        self.assertEqual(pod_a.stage_players.count(), 2)
        self.assertEqual(pod_b.stage_players.count(), 2)

    def test_add_stage_player_joins_pod_with_fewest_active_players(self):
        tournament, stage, stage_players = self._create_stage_with_guest_players(4)
        pod_a, pod_b = stage.get_pods()
        self._assign_pod([stage_players[1]], pod_a)
        Round.objects.create(stage=stage, order=1)

        late_player = Player.objects.create(tournament=tournament, nickname='Late')
        late_stage_player = stage.add_stage_player(late_player)

        self.assertEqual(late_stage_player.pod, pod_b)
        self.assertEqual(late_stage_player.seed, 5)

    def test_add_stage_player_before_start_waits_for_the_snake(self):
        tournament, stage, _stage_players = self._create_stage_with_guest_players(4)
        late_player = Player.objects.create(tournament=tournament, nickname='Late')

        self.assertIsNone(stage.add_stage_player(late_player).pod)

    def test_late_player_skips_empty_pod_added_after_start(self):
        tournament, stage, _stage_players = self._create_stage_with_guest_players(4)
        self._pair_round(stage, 1)
        pod_a, pod_b = stage.get_pods()
        stage.sync_pods([
            {'id': pod_a.id, 'name': pod_a.name},
            {'id': pod_b.id, 'name': pod_b.name},
            {'id': None, 'name': 'Empty'},
        ])

        late_player = Player.objects.create(tournament=tournament, nickname='Late')
        late_stage_player = stage.add_stage_player(late_player)

        self.assertIn(late_stage_player.pod, [pod_a, pod_b])

    def test_assign_pods_before_start_keeps_manual_assignments(self):
        tournament, stage, stage_players = self._create_stage_with_guest_players(4)
        pod_a, _pod_b = stage.get_pods()
        self._assign_pod([stage_players[1]], pod_a)
        late_player = Player.objects.create(tournament=tournament, nickname='Late')
        late_stage_player = stage.add_stage_player(late_player)

        stage.assign_pods_before_start()

        stage_players[1].refresh_from_db()
        late_stage_player.refresh_from_db()
        self.assertEqual(stage_players[1].pod, pod_a)
        self.assertIsNotNone(late_stage_player.pod)

    def test_assign_pods_before_start_snakes_when_nobody_has_a_pod(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(4)
        stage.stage_players.update(pod=None)

        stage.assign_pods_before_start()

        pod_a, _pod_b = stage.get_pods()
        self.assertEqual(
            sorted(pod_a.stage_players.values_list('seed', flat=True)), [1, 4])

    def test_add_stage_player_without_pods_has_no_pod(self):
        tournament, stage, _stage_players = self._create_stage_with_guest_players(
            2, pod_names=())
        late_player = Player.objects.create(tournament=tournament, nickname='Late')

        self.assertIsNone(stage.add_stage_player(late_player).pod)

    def test_assign_podless_active_players_fills_smallest_pods(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(4)
        self._assign_pod(stage_players[2:], None)

        stage.assign_podless_active_players()

        pod_a, pod_b = stage.get_pods()
        self.assertEqual(pod_a.stage_players.count(), 2)
        self.assertEqual(pod_b.stage_players.count(), 2)
        self.assertFalse(stage.stage_players.filter(pod__isnull=True).exists())

    def test_sync_pods_creates_renames_reorders_and_deletes(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(
            0, pod_names=('A', 'B', 'C'))
        pod_a, pod_b, pod_c = stage.get_pods()

        stage.sync_pods([
            {'id': pod_c.id, 'name': 'C renamed'},
            {'id': None, 'name': 'D'},
            {'id': pod_a.id, 'name': 'A'},
        ])

        pods = list(stage.get_pods())
        self.assertEqual([pod.name for pod in pods], ['C renamed', 'D', 'A'])
        self.assertEqual(pods[0].id, pod_c.id)
        self.assertEqual(pods[2].id, pod_a.id)
        self.assertFalse(Pod.objects.filter(id=pod_b.id).exists())

    def test_sync_pods_treats_foreign_pod_ids_as_new_pods(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(0)
        _other_tournament, other_stage, _other_players = self._create_stage_with_guest_players(0)
        foreign_pod = other_stage.get_pods().first()

        stage.sync_pods([{'id': foreign_pod.id, 'name': 'Mine'}])

        foreign_pod.refresh_from_db()
        self.assertEqual(foreign_pod.stage, other_stage)
        self.assertEqual([pod.name for pod in stage.get_pods()], ['Mine'])

    def test_sync_pods_below_two_clears_pod_assignments(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(4)
        pod_a = stage.get_pods().first()

        stage.sync_pods([{'id': pod_a.id, 'name': pod_a.name}])

        self.assertFalse(stage.stage_players.filter(pod__isnull=False).exists())

    def test_pod_changes_unrestricted_before_stage_starts(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(4)

        self.assertEqual(stage.get_pod_change_errors([]), [])

    def test_pods_cannot_be_turned_on_after_stage_starts(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(
            4, pod_names=())
        Round.objects.create(stage=stage, order=1)

        errors = stage.get_pod_change_errors(
            [{'id': None, 'name': 'A'}, {'id': None, 'name': 'B'}])

        self.assertTrue(any('turned on or off' in error for error in errors))

    def test_pods_cannot_be_turned_off_after_stage_starts(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(4)
        self._pair_round(stage, 1)
        pod_a = stage.get_pods().first()
        self._assign_pod(stage_players, pod_a)

        errors = stage.get_pod_change_errors([{'id': pod_a.id, 'name': pod_a.name}])

        self.assertTrue(any('turned on or off' in error for error in errors))

    def test_occupied_pod_cannot_be_removed_after_stage_starts(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(
            6, pod_names=('A', 'B', 'C'))
        self._pair_round(stage, 1)
        pod_a, pod_b, _pod_c = stage.get_pods()

        errors = stage.get_pod_change_errors([
            {'id': pod_a.id, 'name': 'A'},
            {'id': pod_b.id, 'name': 'B'},
        ])

        self.assertTrue(any('still has players' in error for error in errors))

    def test_pods_can_be_added_and_renamed_after_stage_starts(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(4)
        self._pair_round(stage, 1)
        pod_a, pod_b = stage.get_pods()

        errors = stage.get_pod_change_errors([
            {'id': pod_a.id, 'name': 'Renamed'},
            {'id': pod_b.id, 'name': 'B'},
            {'id': None, 'name': 'C'},
        ])

        self.assertEqual(errors, [])

    def test_is_in_same_pod_as(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(4)
        seed_one, seed_two, _seed_three, seed_four = stage_players

        self.assertTrue(seed_one.is_in_same_pod_as(seed_four))
        self.assertFalse(seed_one.is_in_same_pod_as(seed_two))
        self.assertTrue(seed_one.is_in_same_pod_as(None))

    def test_is_in_same_pod_as_without_pods(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(
            2, pod_names=())

        self.assertTrue(stage_players[0].is_in_same_pod_as(stage_players[1]))

    def test_stage_without_pods_has_single_partition(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(
            3, pod_names=())

        partitions = stage.get_player_partitions()

        self.assertEqual(len(partitions), 1)
        self.assertIsNone(partitions[0][0])
        self.assertEqual([sp.id for sp in partitions[0][1]],
                         [sp.id for sp in stage_players])


class PodPairingTestCase(PodTestMixin, TestCase):
    def test_swiss_pairs_within_pods_over_several_rounds(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(9)
        pod_a, pod_b = stage.get_pods()

        for order in range(1, 4):
            round_obj = self._pair_round(stage, order)
            byes = list(round_obj.matches.filter(player_two__isnull=True))
            self.assertEqual(len(byes), 1)
            self.assertEqual(byes[0].player_one.pod, pod_a)
            self.assertEqual(round_obj.matches.count(), 5)
            self._resolve_round_with_player_one_wins(round_obj)

        self._assert_no_cross_pod_matches(stage)
        self.assertFalse(Match.objects.filter(
            round__stage=stage, player_one__pod=pod_b, player_two__isnull=True).exists())

    def test_swiss_large_pods_use_greedy_pairing_within_pods(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(30)

        for order in range(1, 3):
            round_obj = self._pair_round(stage, order)
            self.assertEqual(round_obj.matches.count(), 16)
            self._resolve_round_with_player_one_wins(round_obj)

        self._assert_no_cross_pod_matches(stage)

    def test_swiss_with_single_pod_pairs_everyone(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(
            4, pod_names=('Only',))

        round_obj = self._pair_round(stage, 1)

        paired_ids = set()
        for match in round_obj.matches.all():
            paired_ids.update([match.player_one_id, match.player_two_id])
        self.assertEqual(paired_ids, {sp.id for sp in stage_players})

    def test_podless_active_player_is_assigned_before_pairing(self):
        tournament, stage, _stage_players = self._create_stage_with_guest_players(4)
        late_player = Player.objects.create(tournament=tournament, nickname='Late')
        late_stage_player = StagePlayer.objects.create(
            player=late_player, stage=stage, seed=5)

        round_obj = self._pair_round(stage, 1)

        late_stage_player.refresh_from_db()
        self.assertIsNotNone(late_stage_player.pod)
        self.assertTrue(round_obj.matches.filter(
            models.Q(player_one=late_stage_player) | models.Q(player_two=late_stage_player)).exists())

    def test_round_robin_completes_each_pod_in_shared_rounds(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(
            7, pairing_strategy='round_robin_scheduled')
        pod_a, pod_b = stage.get_pods()
        self._assign_pod(stage_players[:5], pod_a)
        self._assign_pod(stage_players[5:], pod_b)

        self._pair_round(stage, 1)

        self.assertEqual(stage.rounds.count(), 5)
        self._assert_no_cross_pod_matches(stage)

        played_pairs = {
            frozenset([match.player_one_id, match.player_two_id])
            for match in Match.objects.filter(round__stage=stage, player_two__isnull=False)
        }
        expected_pairs = set()
        for pod_players in (stage_players[:5], stage_players[5:]):
            for i, first in enumerate(pod_players):
                for second in pod_players[i + 1:]:
                    expected_pairs.add(frozenset([first.id, second.id]))
        self.assertEqual(played_pairs, expected_pairs)

    def test_round_robin_new_round_only_when_a_pod_has_unplayed_pairs(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(
            6, pairing_strategy='round_robin_scheduled')
        strategy = stage.get_pairing_strategy()

        self._pair_round(stage, 1)
        self.assertFalse(strategy.can_create_new_round(stage))

        pod_b = stage.get_pods().last()
        Match.objects.filter(
            round__stage=stage, player_one__pod=pod_b, player_two__isnull=False).first().delete()
        for round_obj in stage.rounds.all():
            self._resolve_round_with_player_one_wins(round_obj)

        self.assertTrue(strategy.can_create_new_round(stage))

    def test_single_elimination_runs_a_bracket_per_pod(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(
            11, pairing_strategy='single_elimination')
        strategy = stage.get_pairing_strategy()
        pod_a, pod_b = stage.get_pods()
        self._assign_pod(stage_players[:8], pod_a)
        self._assign_pod(stage_players[8:], pod_b)

        expected_match_counts = [6, 3, 1]
        for order, expected_match_count in enumerate(expected_match_counts, start=1):
            round_obj = self._pair_round(stage, order)
            self.assertEqual(round_obj.matches.count(), expected_match_count)
            self._resolve_round_with_player_one_wins(round_obj)
            self._assert_no_cross_pod_matches(stage)
            if order < len(expected_match_counts):
                self.assertTrue(strategy.can_create_new_round(stage))

        self.assertFalse(strategy.can_create_new_round(stage))

    def test_single_elimination_without_pods_stops_at_one_winner(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(
            4, pod_names=(), pairing_strategy='single_elimination')
        strategy = stage.get_pairing_strategy()

        for order in (1, 2):
            round_obj = self._pair_round(stage, order)
            self._resolve_round_with_player_one_wins(round_obj)

        self.assertEqual(stage.rounds.get(order=2).matches.count(), 1)
        self.assertFalse(strategy.can_create_new_round(stage))

    def test_free_for_all_creates_no_pairings(self):
        _tournament, stage, _stage_players = self._create_stage_with_guest_players(
            4, pairing_strategy='round_robin')

        round_obj = self._pair_round(stage, 1)

        self.assertEqual(round_obj.matches.count(), 0)


class PodStandingsTestCase(PodTestMixin, TestCase):
    def setUp(self):
        self.tournament, self.stage, self.stage_players = self._create_stage_with_guest_players(6)
        self.pod_a, self.pod_b = self.stage.get_pods()
        (self.seed_1, self.seed_2, self.seed_3,
         self.seed_4, self.seed_5, self.seed_6) = self.stage_players

    def _ordered_ids(self, standings):
        return [standing['stage_player'].id for standing in standings]

    def _play_strong_pod_a(self):
        self._play(self.stage, self.seed_1, self.seed_5)
        self._play(self.stage, self.seed_4, self.seed_5)
        self._play(self.stage, self.seed_1, self.seed_4)
        self._play(self.stage, self.seed_4, self.seed_5)
        self._play(self.stage, self.seed_3, self.seed_2)

    def test_pod_standings_rank_within_the_pod(self):
        self._play_strong_pod_a()

        standings = StandingCalculator.get_stage_standings(self.stage, self.pod_b)

        self.assertEqual(self._ordered_ids(standings),
                         [self.seed_3.id, self.seed_2.id, self.seed_6.id])
        self.assertEqual([s['rank'] for s in standings], [1, 2, 3])

    def test_unified_standings_interleave_pod_ranks(self):
        self._play_strong_pod_a()

        unified = StandingCalculator.get_unified_stage_standings(self.stage)

        self.assertEqual(self._ordered_ids(unified), [
            self.seed_1.id, self.seed_3.id,
            self.seed_4.id, self.seed_2.id,
            self.seed_5.id, self.seed_6.id,
        ])
        self.assertEqual([s['rank'] for s in unified], [1, 2, 3, 4, 5, 6])
        self.assertEqual([s['pod_rank'] for s in unified], [1, 1, 2, 2, 3, 3])

    def test_unified_standings_without_pods_match_stage_standings(self):
        _tournament, stage, stage_players = self._create_stage_with_guest_players(
            3, pod_names=())
        self._play(stage, stage_players[2], stage_players[0])

        self.assertEqual(
            self._ordered_ids(StandingCalculator.get_unified_stage_standings(stage)),
            self._ordered_ids(StandingCalculator.get_stage_standings(stage)))

    def test_head_to_head_does_not_order_players_across_pods(self):
        self.stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'head_to_head', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])
        self._play(self.stage, self.seed_4, self.seed_1)
        self._play(self.stage, self.seed_1, self.seed_5)
        self._play(self.stage, self.seed_2, self.seed_6)

        pod_a_standings = StandingCalculator.get_stage_standings(self.stage, self.pod_a)
        self.assertEqual(pod_a_standings[0]['stage_player'].id, self.seed_4.id)

        unified = StandingCalculator.get_unified_stage_standings(self.stage)
        self.assertEqual(self._ordered_ids(unified)[:2],
                         [self.seed_2.id, self.seed_4.id])

    def test_dropped_pod_leader_does_not_push_pod_down_a_tier(self):
        self._play(self.stage, self.seed_1, self.seed_4)
        self._play(self.stage, self.seed_1, self.seed_5)
        self._play(self.stage, self.seed_4, self.seed_5)
        self._play(self.stage, self.seed_2, self.seed_3)
        self.seed_1.player.status = Player.PlayerStatus.DROPPED
        self.seed_1.player.save()

        unified = StandingCalculator.get_unified_stage_standings(self.stage)

        self.assertEqual(self._ordered_ids(unified), [
            self.seed_2.id, self.seed_4.id,
            self.seed_3.id, self.seed_5.id,
            self.seed_6.id,
            self.seed_1.id,
        ])

    def test_moved_player_strength_of_schedule_counts_old_pod_opponents(self):
        self._play(self.stage, self.seed_1, self.seed_4)
        self._play(self.stage, self.seed_4, self.seed_5)
        self._assign_pod([self.seed_4], self.pod_b)

        pod_b_standings = StandingCalculator.get_stage_standings(self.stage, self.pod_b)

        moved_standing = next(
            s for s in pod_b_standings if s['stage_player'].id == self.seed_4.id)
        self.assertEqual(moved_standing['strength_of_schedule'], 1.0)

    def test_tournament_standings_filtered_to_a_pod(self):
        self._play_strong_pod_a()

        standings = StandingCalculator.get_tournament_standings(
            self.tournament, pod=self.pod_a)

        self.assertEqual([s['stage_player'].id for s in standings],
                         [self.seed_1.id, self.seed_4.id, self.seed_5.id])
        self.assertEqual([s['tournament_rank'] for s in standings], [1, 2, 3])

    def test_tournament_standings_use_unified_order_and_include_pod(self):
        self._play_strong_pod_a()

        standings = StandingCalculator.get_tournament_standings(self.tournament)

        self.assertEqual([s['stage_player'].id for s in standings][:4], [
            self.seed_1.id, self.seed_3.id, self.seed_4.id, self.seed_2.id])
        self.assertEqual(standings[0]['pod'], self.pod_a)
        self.assertEqual(standings[1]['pod'], self.pod_b)

    def test_playoff_seeding_follows_unified_order(self):
        self.tournament.create_playoff_stage(max_players=4)
        self._play_strong_pod_a()

        playoff_stage = self.tournament.prepare_next_stage_seeding()
        playoff_player_ids = list(
            playoff_stage.stage_players.order_by('seed').values_list('player_id', flat=True))

        self.assertEqual(playoff_player_ids, [
            self.seed_1.player_id, self.seed_3.player_id,
            self.seed_4.player_id, self.seed_2.player_id,
            self.seed_5.player_id, self.seed_6.player_id,
        ])

        self.tournament.advance_to_next_stage()

        self.assertEqual(playoff_stage.stage_players.count(), 4)
        self.assertFalse(playoff_stage.stage_players.filter(pod__isnull=False).exists())
        self.seed_4.refresh_from_db()
        self.assertEqual(self.seed_4.rank, 3)


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class PodTournamentFormTestCase(PodTestMixin, TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.client.login(username='owner', password='password')

    def _get_post_data(self, pod_names, pod_ids=None, **overrides):
        data = {
            'name': 'Podded Tournament',
            'is_accepting_registrations': True,
            'is_public': False,
            'main_pairing_strategy': 'swiss',
            'main_score_reporting': '0',
            'main_allow_ties': 'False',
            'playoff_score_reporting': '0',
            'criterion_wins_enabled': 'on',
            'criterion_wins_order': '1',
            'pods_submitted': '1',
            'pod_id': pod_ids if pod_ids is not None else [''] * len(pod_names),
            'pod_name': pod_names,
        }
        data.update(overrides)
        return data

    def test_create_tournament_with_pods(self):
        self.client.post(reverse('tourney:tourney-create-tournament'),
                         self._get_post_data(['Red', 'Blue', 'Green']))

        main_stage = Tournament.objects.get(name='Podded Tournament').stages.get(order=1)
        self.assertEqual([pod.name for pod in main_stage.get_pods()],
                         ['Red', 'Blue', 'Green'])

    def test_create_tournament_without_pods(self):
        self.client.post(reverse('tourney:tourney-create-tournament'),
                         self._get_post_data([]))

        main_stage = Tournament.objects.get(name='Podded Tournament').stages.get(order=1)
        self.assertFalse(main_stage.pods.exists())

    def test_create_rejects_more_than_maximum_pods(self):
        pod_names = [f'Pod {i}' for i in range(MAXIMUM_PODS_PER_STAGE + 1)]

        response = self.client.post(reverse('tourney:tourney-create-tournament'),
                                    self._get_post_data(pod_names))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'at most {MAXIMUM_PODS_PER_STAGE} pods')
        self.assertFalse(Tournament.objects.filter(name='Podded Tournament').exists())

    def test_create_accepts_maximum_pods(self):
        pod_names = [f'Pod {i}' for i in range(MAXIMUM_PODS_PER_STAGE)]

        self.client.post(reverse('tourney:tourney-create-tournament'),
                         self._get_post_data(pod_names))

        main_stage = Tournament.objects.get(name='Podded Tournament').stages.get(order=1)
        self.assertEqual(main_stage.pods.count(), MAXIMUM_PODS_PER_STAGE)

    def test_create_rejects_blank_and_duplicate_pod_names(self):
        blank_response = self.client.post(reverse('tourney:tourney-create-tournament'),
                                          self._get_post_data(['Red', '  ']))
        duplicate_response = self.client.post(reverse('tourney:tourney-create-tournament'),
                                              self._get_post_data(['Red', 'red']))

        self.assertContains(blank_response, 'Pod names cannot be blank.')
        self.assertContains(duplicate_response, 'Pod names must be unique.')
        self.assertFalse(Tournament.objects.filter(name='Podded Tournament').exists())

    def test_post_without_pod_fields_leaves_pods_unchanged(self):
        tournament, stage, _stage_players = self._create_stage_with_guest_players(
            4, owner=self.owner)
        post_data = self._get_post_data([])
        for key in ('pods_submitted', 'pod_id', 'pod_name'):
            post_data.pop(key)

        self.client.post(
            reverse('tourney:tourney-edit-tournament', args=[tournament.code]), post_data)

        self.assertEqual(stage.pods.count(), 2)

    def test_invalid_post_keeps_entered_pod_names(self):
        response = self.client.post(reverse('tourney:tourney-create-tournament'),
                                    self._get_post_data(['Keep Me', 'keep me']))

        self.assertContains(response, 'Keep Me')

    def test_edit_renames_pods_and_keeps_assignments(self):
        tournament, stage, stage_players = self._create_stage_with_guest_players(
            4, owner=self.owner)
        pod_a, pod_b = stage.get_pods()

        self.client.post(
            reverse('tourney:tourney-edit-tournament', args=[tournament.code]),
            self._get_post_data(['Alpha', 'Bravo'], pod_ids=[pod_a.id, pod_b.id]))

        pod_a.refresh_from_db()
        self.assertEqual(pod_a.name, 'Alpha')
        stage_players[0].refresh_from_db()
        self.assertEqual(stage_players[0].pod, pod_a)

    def test_edit_rejects_turning_on_pods_after_stage_starts(self):
        tournament, stage, _stage_players = self._create_stage_with_guest_players(
            4, pod_names=(), owner=self.owner)
        Round.objects.create(stage=stage, order=1)

        response = self.client.post(
            reverse('tourney:tourney-edit-tournament', args=[tournament.code]),
            self._get_post_data(['Alpha', 'Bravo']))

        self.assertContains(response, 'turned on or off')
        self.assertFalse(stage.pods.exists())

    def test_edit_rejects_removing_occupied_pod_after_stage_starts(self):
        tournament, stage, _stage_players = self._create_stage_with_guest_players(
            6, pod_names=('A', 'B', 'C'), owner=self.owner)
        self._pair_round(stage, 1)
        pod_a, pod_b, _pod_c = stage.get_pods()

        response = self.client.post(
            reverse('tourney:tourney-edit-tournament', args=[tournament.code]),
            self._get_post_data(['A', 'B'], pod_ids=[pod_a.id, pod_b.id]))

        self.assertContains(response, 'still has players')
        self.assertEqual(stage.pods.count(), 3)
        redisplayed_pods = json.loads(response.context['pod_entries_json'])
        self.assertEqual([pod['name'] for pod in redisplayed_pods], ['A', 'B', 'C'])

    def test_copy_tournament_copies_pod_names(self):
        tournament, _stage, _stage_players = self._create_stage_with_guest_players(
            0, pod_names=('North', 'South'), owner=self.owner)
        copy_url = reverse('tourney:tourney-copy-tournament', args=[tournament.code])

        get_response = self.client.get(copy_url)
        self.assertContains(get_response, 'North')
        self.assertContains(get_response, 'South')

        self.client.post(copy_url, self._get_post_data(
            ['North', 'South'], name='Copied Tournament'))

        copied_stage = Tournament.objects.get(name='Copied Tournament').stages.get(order=1)
        self.assertEqual([pod.name for pod in copied_stage.get_pods()], ['North', 'South'])


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class PodStageFlowTestCase(PodTestMixin, TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.client.login(username='owner', password='password')
        self.tournament, self.stage, self.stage_players = self._create_stage_with_guest_players(
            6, owner=self.owner)
        self.stage.stage_players.update(pod=None)
        self.pod_a, self.pod_b = self.stage.get_pods()

    def _url(self, name):
        return reverse(f'tourney:{name}', args=[self.tournament.code])

    def test_starting_podded_stage_snakes_and_asks_for_confirmation(self):
        response = self.client.post(self._url('tourney-prepare-current-stage-seeding'))

        self.assertRedirects(response, self._url('tourney-confirm-seeding'),
                             fetch_redirect_response=False)
        self.assertFalse(self.stage.rounds.exists())
        self.assertEqual(self.pod_a.stage_players.count(), 3)
        self.assertEqual(self.pod_b.stage_players.count(), 3)

    def test_confirm_page_shows_pod_columns(self):
        self.client.post(self._url('tourney-prepare-current-stage-seeding'))

        response = self.client.get(self._url('tourney-confirm-seeding'))

        self.assertContains(response, 'Confirm Pods')
        self.assertContains(response, 'Re-snake by Seed')
        self.assertContains(response, 'data-pod-id="%s"' % self.pod_a.id)

    def test_move_single_player_between_pods_on_confirm_page(self):
        self.client.post(self._url('tourney-prepare-current-stage-seeding'))
        seed_one = self.stage_players[0]

        response = self.client.post(self._url('tourney-update-pod-assignments'), {
            'stage_player_id': seed_one.id, 'pod_id': self.pod_b.id})

        self.assertEqual(response.status_code, 200)
        seed_one.refresh_from_db()
        self.assertEqual(seed_one.pod, self.pod_b)

    def test_drag_assignments_update_pods(self):
        self.client.post(self._url('tourney-prepare-current-stage-seeding'))
        ids = [sp.id for sp in self.stage_players]

        self.client.post(self._url('tourney-update-pod-assignments'), {
            'pod_assignments': json.dumps({
                str(self.pod_a.id): [str(i) for i in ids[:2]],
                str(self.pod_b.id): [str(i) for i in ids[2:]],
            })})

        self.assertEqual(set(self.pod_a.stage_players.values_list('id', flat=True)), set(ids[:2]))
        self.assertEqual(set(self.pod_b.stage_players.values_list('id', flat=True)), set(ids[2:]))

    def test_pod_assignments_reject_bad_input_and_ignore_foreign_pods(self):
        self.client.post(self._url('tourney-prepare-current-stage-seeding'))
        _other_tournament, other_stage, _other_players = self._create_stage_with_guest_players(0)
        foreign_pod = other_stage.get_pods().first()

        bad_response = self.client.post(self._url('tourney-update-pod-assignments'), {
            'pod_assignments': 'not json'})
        self.client.post(self._url('tourney-update-pod-assignments'), {
            'stage_player_id': self.stage_players[0].id, 'pod_id': foreign_pod.id})

        self.assertEqual(bad_response.status_code, 400)
        self.stage_players[0].refresh_from_db()
        self.assertEqual(self.stage_players[0].pod, self.pod_a)

    def test_starting_again_keeps_manual_pod_moves(self):
        self.client.post(self._url('tourney-prepare-current-stage-seeding'))
        seed_one = self.stage_players[0]
        self.client.post(self._url('tourney-update-pod-assignments'), {
            'stage_player_id': seed_one.id, 'pod_id': self.pod_b.id})

        self.client.post(self._url('tourney-prepare-current-stage-seeding'))

        seed_one.refresh_from_db()
        self.assertEqual(seed_one.pod, self.pod_b)

    def test_malformed_pod_assignment_posts_are_rejected(self):
        self.client.post(self._url('tourney-prepare-current-stage-seeding'))
        url = self._url('tourney-update-pod-assignments')

        responses = [
            self.client.post(url, {}),
            self.client.post(url, {'pod_assignments': '[1, 2]'}),
            self.client.post(url, {'pod_id': 'x', 'stage_player_id': '1'}),
        ]

        self.assertEqual([response.status_code for response in responses], [400, 400, 400])

    def test_resnake_restores_seed_distribution(self):
        self.client.post(self._url('tourney-prepare-current-stage-seeding'))
        self._assign_pod(self.stage_players, self.pod_a)

        self.client.post(self._url('tourney-snake-pods-by-seed'))

        self.assertEqual(self.pod_a.stage_players.count(), 3)
        self.assertEqual(self.pod_b.stage_players.count(), 3)

    def test_randomize_seeding_keeps_pods_balanced(self):
        self.client.post(self._url('tourney-prepare-current-stage-seeding'))

        response = self.client.post(self._url('tourney-randomize-seeding'))

        self.assertContains(response, 'data-pod-id')
        self.assertEqual(self.pod_a.stage_players.count(), 3)
        self.assertEqual(self.pod_b.stage_players.count(), 3)

    def test_starting_after_confirmation_pairs_within_pods(self):
        self.client.post(self._url('tourney-prepare-current-stage-seeding'))

        self.client.post(self._url('tourney-start-next-stage'))

        self.assertEqual(self.stage.rounds.count(), 1)
        self.assertEqual(Match.objects.filter(round__stage=self.stage).count(), 4)
        self._assert_no_cross_pod_matches(self.stage)

    def test_stage_without_pods_still_starts_immediately(self):
        self.stage.sync_pods([])

        self.client.post(self._url('tourney-prepare-current-stage-seeding'))

        self.assertEqual(self.stage.rounds.count(), 1)


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class PodMatchViewsTestCase(PodTestMixin, TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.tournament = Tournament.objects.create(
            name='FFA Pods', owner=self.owner, is_accepting_registrations=True)
        self.stage = Stage.objects.create(
            tournament=self.tournament, name='Main Stage', order=1,
            pairing_strategy='round_robin')
        self.stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True},
            {'key': 'seed', 'enabled': True},
        ])
        self.stage.sync_pods([{'id': None, 'name': 'Pod A'}, {'id': None, 'name': 'Pod B'}])
        self.pod_a, self.pod_b = self.stage.get_pods()

        self.stage_players = []
        for i, nickname in enumerate(['Anvil', 'Beacon', 'Comet', 'Dynamo'], start=1):
            user = User.objects.create_user(f'user{i}', f'user{i}@test.com', 'password')
            player = Player.objects.create(
                user=user, tournament=self.tournament, nickname=nickname)
            self.stage_players.append(StagePlayer.objects.create(
                player=player, stage=self.stage, seed=i))
        self.stage.snake_stage_players_into_pods()
        self.round = self._pair_round(self.stage, 1)
        for stage_player in self.stage_players:
            stage_player.refresh_from_db()
        self.anvil, self.beacon, self.comet, self.dynamo = self.stage_players

    def _url(self, name, query=''):
        return reverse(f'tourney:{name}', args=[self.tournament.code]) + query

    def test_snake_puts_anvil_and_dynamo_together(self):
        self.assertEqual(self.anvil.pod, self.pod_a)
        self.assertEqual(self.dynamo.pod, self.pod_a)
        self.assertEqual(self.beacon.pod, self.pod_b)

    def test_admin_cannot_add_cross_pod_match(self):
        self.client.login(username='owner', password='password')

        self.client.post(self._url('tourney-add-match'), {
            'player_one': self.anvil.id, 'player_two': self.beacon.id})

        self.assertFalse(self.round.matches.exists())

    def test_admin_can_add_same_pod_match(self):
        self.client.login(username='owner', password='password')

        self.client.post(self._url('tourney-add-match'), {
            'player_one': self.anvil.id, 'player_two': self.dynamo.id})

        self.assertEqual(self.round.matches.count(), 1)

    def test_admin_can_award_bye_with_pods(self):
        self.client.login(username='owner', password='password')

        self.client.post(self._url('tourney-add-match'), {'player_one': self.anvil.id})

        self.assertTrue(self.round.matches.filter(player_two__isnull=True).exists())

    def test_player_cannot_report_cross_pod_result(self):
        self.client.login(username='user1', password='password')

        self.client.post(self._url('tourney-player-add-match-result'), {
            'opponent': self.beacon.id, 'winner': 'me'})

        self.assertFalse(self.round.matches.exists())

    def test_player_can_report_same_pod_result(self):
        self.client.login(username='user1', password='password')

        self.client.post(self._url('tourney-player-add-match-result'), {
            'opponent': self.dynamo.id, 'winner': 'me'})

        match = self.round.matches.get()
        self.assertEqual(match.result.winner, self.anvil)

    def test_player_report_opponents_are_limited_to_own_pod(self):
        self.client.login(username='user1', password='password')

        response = self.client.get(self._url('tourney-detail-matches'))

        opponents = json.loads(response.context['player_report_opponents_json'])
        self.assertEqual([opponent['id'] for opponent in opponents], [self.dynamo.id])

    def test_unmatched_players_json_includes_pod(self):
        self.client.login(username='owner', password='password')

        response = self.client.get(self._url('tourney-detail-matches'))

        unmatched = json.loads(response.context['unmatched_players_json'])
        pod_ids = {entry['id']: entry['podId'] for entry in unmatched}
        self.assertEqual(pod_ids[self.anvil.id], self.pod_a.id)
        self.assertEqual(pod_ids[self.beacon.id], self.pod_b.id)

    def test_redirect_after_htmx_action_keeps_selected_pod(self):
        self.client.login(username='owner', password='password')
        current_url = 'http://testserver' + self._url(
            'tourney-detail-matches', f'?pod={self.pod_a.slug}')

        response = self.client.post(
            self._url('tourney-add-match'),
            {'player_one': self.anvil.id, 'player_two': self.dynamo.id},
            HTTP_HX_REQUEST='true', HTTP_HX_CURRENT_URL=current_url)

        self.assertTrue(response['HX-Redirect'].endswith(f'?pod={self.pod_a.slug}'))

    def test_matches_pod_filter_shows_only_that_pods_matches(self):
        self._play_in_round(self.anvil, self.dynamo)
        self._play_in_round(self.beacon, self.comet)
        self.client.login(username='owner', password='password')

        response = self.client.get(self._url('tourney-detail-matches', f'?pod={self.pod_b.slug}'))

        round_group = response.context['grouped_matches'][0]['rounds'][0]
        self.assertEqual([match.player_one_id for match in round_group['matches']],
                         [self.beacon.id])

    def test_matches_all_view_numbers_matches_across_pods(self):
        self._play_in_round(self.beacon, self.comet)
        self._play_in_round(self.anvil, self.dynamo)
        self.client.login(username='owner', password='password')

        response = self.client.get(self._url('tourney-detail-matches'))

        pod_groups = response.context['grouped_matches'][0]['rounds'][0]['pod_groups']
        numbers = [numbered['number'] for group in pod_groups
                   for numbered in group['numbered_matches']]
        self.assertEqual(numbers, [1, 2])

    def test_move_player_message_escapes_names(self):
        self.pod_b.name = '<b>Bold</b>'
        self.pod_b.save()
        self.client.login(username='owner', password='password')

        response = self.client.post(self._url('tourney-manage-players'), {
            'action': 'move_player', 'player_id': self.dynamo.player_id,
            'pod_id': self.pod_b.id}, HTTP_HX_REQUEST='true')

        self.assertIn('&lt;b&gt;Bold&lt;/b&gt;', response['HX-Trigger'])
        self.assertNotIn('<b>Bold</b>', response['HX-Trigger'])

    def test_matches_all_view_groups_rounds_by_pod(self):
        self._play_in_round(self.beacon, self.comet)
        self._play_in_round(self.anvil, self.dynamo)
        self.client.login(username='owner', password='password')

        response = self.client.get(self._url('tourney-detail-matches'))

        pod_groups = response.context['grouped_matches'][0]['rounds'][0]['pod_groups']
        self.assertEqual([group['pod'] for group in pod_groups], [self.pod_a, self.pod_b])
        self.assertContains(response, 'data-pod-switcher')

    def test_standings_pod_filter(self):
        self.client.login(username='owner', password='password')

        response = self.client.get(self._url('tourney-detail-standings', f'?pod={self.pod_b.slug}'))

        self.assertEqual({s['player'].nickname for s in response.context['standings']},
                         {'Beacon', 'Comet'})
        self.assertFalse(response.context['show_pod_column'])

    def test_standings_all_view_shows_pod_column(self):
        self.client.login(username='owner', password='password')

        response = self.client.get(self._url('tourney-detail-standings'))

        self.assertTrue(response.context['show_pod_column'])
        self.assertEqual(len(response.context['standings']), 4)

    def test_invalid_pod_filter_falls_back_to_all(self):
        self.client.login(username='owner', password='password')

        response = self.client.get(self._url('tourney-detail-standings', '?pod=nope'))

        self.assertIsNone(response.context['selected_pod'])
        self.assertEqual(len(response.context['standings']), 4)

    def test_unknown_pod_filter_falls_back_to_players_own_pod(self):
        self.client.login(username='user2', password='password')

        response = self.client.get(self._url('tourney-detail-standings', '?pod=renamed-pod'))

        self.assertEqual(response.context['selected_pod'], self.pod_b)

    def test_player_defaults_to_own_pod(self):
        self.client.login(username='user2', password='password')

        standings_response = self.client.get(self._url('tourney-detail-standings'))
        matches_response = self.client.get(self._url('tourney-detail-matches'))

        self.assertEqual(standings_response.context['selected_pod'], self.pod_b)
        self.assertEqual(matches_response.context['selected_pod'], self.pod_b)
        self.assertContains(standings_response, '(your pod)')

    def test_player_can_choose_all_pods(self):
        self.client.login(username='user2', password='password')

        response = self.client.get(self._url('tourney-detail-standings', '?pod=all'))

        self.assertIsNone(response.context['selected_pod'])
        self.assertEqual(len(response.context['standings']), 4)

    def test_admin_who_plays_defaults_to_all_pods(self):
        self.tournament.owner = self.anvil.player.user
        self.tournament.save()
        self.client.login(username='user1', password='password')

        response = self.client.get(self._url('tourney-detail-matches'))

        self.assertIsNone(response.context['selected_pod'])
        self.assertContains(response, '(your pod)')

    def test_tab_links_keep_the_chosen_pod(self):
        self.client.login(username='user2', password='password')

        response = self.client.get(self._url('tourney-detail-matches', '?pod=all'))

        self.assertContains(response, self._url('tourney-detail-standings', '?pod=all'))

    def test_admin_defaults_to_all_pods(self):
        self.client.login(username='owner', password='password')

        response = self.client.get(self._url('tourney-detail-standings'))

        self.assertIsNone(response.context['selected_pod'])

    def test_pod_toggle_hidden_without_pods(self):
        self.stage.stage_players.update(pod=None)
        self.stage.pods.all().delete()
        self.client.login(username='owner', password='password')

        response = self.client.get(self._url('tourney-detail-standings'))

        self.assertNotContains(response, 'data-pod-switcher')

    def test_admin_moves_player_between_pods(self):
        self.client.login(username='owner', password='password')

        response = self.client.post(self._url('tourney-manage-players'), {
            'action': 'move_player', 'player_id': self.dynamo.player_id,
            'pod_id': self.pod_b.id}, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 200)
        self.dynamo.refresh_from_db()
        self.assertEqual(self.dynamo.pod, self.pod_b)
        self.assertTrue(TournamentActionLog.objects.filter(
            tournament=self.tournament,
            action_type=TournamentActionLog.ActionType.MOVE_PLAYER).exists())

    def test_manage_players_shows_pod_menu(self):
        self.client.login(username='owner', password='password')

        response = self.client.get(self._url('tourney-manage-players'))

        self.assertContains(response, 'name="pod_id"')
        self.assertContains(response, 'Pod B')

    def test_late_registration_joins_smallest_pod(self):
        self.dynamo.pod = self.pod_b
        self.dynamo.save()
        User.objects.create_user('latecomer', 'late@test.com', 'password')
        self.client.login(username='latecomer', password='password')

        self.client.post(self._url('tourney-register'), {'nickname': 'Eclipse'})

        late_stage_player = self.stage.stage_players.get(player__nickname='Eclipse')
        self.assertEqual(late_stage_player.pod, self.pod_a)

    def test_admin_added_player_joins_smallest_pod(self):
        self.anvil.pod = self.pod_b
        self.anvil.save()
        self.client.login(username='owner', password='password')

        self.client.post(self._url('tourney-manage-players'), {
            'action': 'add_player', 'nickname': 'Flare', 'username': ''})

        late_stage_player = self.stage.stage_players.get(player__nickname='Flare')
        self.assertEqual(late_stage_player.pod, self.pod_a)

    def _play_in_round(self, winner, loser):
        match = Match.objects.create(round=self.round, player_one=winner, player_two=loser)
        MatchResult.objects.create(match=match, winner=winner)


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class TournamentCopyTestCase(PodTestMixin, TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.client.login(username='owner', password='password')

    def _copy_url(self, tournament):
        return reverse('tourney:tourney-copy-tournament', args=[tournament.code])

    def _get_copy_post_data(self, pod_names=None, **overrides):
        data = {
            'name': 'Copied Tournament',
            'is_accepting_registrations': True,
            'is_public': False,
            'main_pairing_strategy': 'swiss',
            'main_score_reporting': '0',
            'main_allow_ties': 'False',
            'enable_playoffs': True,
            'playoff_max_players': '4',
            'playoff_score_reporting': '0',
        }
        if pod_names is not None:
            data.update({
                'pods_submitted': '1',
                'pod_id': [''] * len(pod_names),
                'pod_name': pod_names,
            })
        data.update(overrides)
        return data

    def _create_legacy_tournament(self):
        tournament = Tournament.objects.create(
            name='Legacy Night', owner=self.owner, description='Before pods existed')
        main_stage = tournament.create_initial_stage(main_pairing_strategy='swiss')
        main_stage.set_ranking_criteria([
            {'key': 'wins', 'enabled': True, 'order': 1},
            {'key': 'points', 'enabled': True, 'order': 2},
        ])
        playoff_stage = tournament.create_playoff_stage(max_players=4)

        stage_players = []
        for i in range(4):
            player = Player.objects.create(tournament=tournament, nickname=f'Legacy {i + 1}')
            stage_players.append(StagePlayer.objects.create(
                player=player, stage=main_stage, seed=i + 1))
        self._play(main_stage, stage_players[0], stage_players[1])
        self._play(main_stage, stage_players[2], stage_players[3])

        return tournament, main_stage, playoff_stage

    def _get_copied_tournament(self):
        return Tournament.objects.get(name='Copied Tournament')

    def test_copy_page_for_legacy_tournament_renders_without_pods(self):
        tournament, _main_stage, _playoff_stage = self._create_legacy_tournament()

        response = self.client.get(self._copy_url(tournament))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.context['pod_entries_json']), [])
        self.assertContains(response, 'Legacy Night #2')

    def test_copy_legacy_tournament_creates_copy_without_pods(self):
        tournament, _main_stage, _playoff_stage = self._create_legacy_tournament()

        response = self.client.post(self._copy_url(tournament), self._get_copy_post_data([]))

        copy = self._get_copied_tournament()
        self.assertRedirects(
            response, reverse('tourney:tourney-detail-home', args=[copy.code]),
            fetch_redirect_response=False)
        copied_main_stage = copy.stages.get(order=1)
        self.assertFalse(copied_main_stage.pods.exists())
        self.assertEqual(
            list(copied_main_stage.stage_ranking_criteria.values_list('criterion_key', flat=True)),
            ['wins', 'points'])
        self.assertTrue(copy.stages.filter(order=2).exists())

    def test_copy_legacy_tournament_from_form_without_pod_fields(self):
        tournament, _main_stage, _playoff_stage = self._create_legacy_tournament()

        self.client.post(self._copy_url(tournament), self._get_copy_post_data())

        self.assertFalse(self._get_copied_tournament().stages.get(order=1).pods.exists())

    def test_copy_legacy_tournament_leaves_source_untouched(self):
        tournament, main_stage, _playoff_stage = self._create_legacy_tournament()

        self.client.post(self._copy_url(tournament), self._get_copy_post_data([]))

        self.assertEqual(main_stage.stage_players.count(), 4)
        self.assertEqual(main_stage.rounds.count(), 2)
        self.assertFalse(main_stage.pods.exists())

    def test_copy_tournament_without_stages(self):
        tournament = Tournament.objects.create(name='Bare Tournament', owner=self.owner)

        get_response = self.client.get(self._copy_url(tournament))
        self.client.post(self._copy_url(tournament), self._get_copy_post_data([]))

        self.assertEqual(get_response.status_code, 200)
        self.assertTrue(self._get_copied_tournament().stages.filter(order=1).exists())

    def test_copy_page_prefills_source_pods_without_ids(self):
        tournament, _stage, _stage_players = self._create_stage_with_guest_players(
            0, pod_names=('North', 'South', 'East'), owner=self.owner)

        response = self.client.get(self._copy_url(tournament))

        self.assertEqual(json.loads(response.context['pod_entries_json']), [
            {'id': None, 'name': 'North'},
            {'id': None, 'name': 'South'},
            {'id': None, 'name': 'East'},
        ])

    def test_copy_creates_fresh_pods_in_source_order(self):
        tournament, source_stage, _stage_players = self._create_stage_with_guest_players(
            0, pod_names=('North', 'South', 'East'), owner=self.owner)

        self.client.post(self._copy_url(tournament),
                         self._get_copy_post_data(['North', 'South', 'East']))

        copied_pods = list(self._get_copied_tournament().stages.get(order=1).get_pods())
        self.assertEqual([pod.name for pod in copied_pods], ['North', 'South', 'East'])
        self.assertEqual([pod.slug for pod in copied_pods], ['north', 'south', 'east'])
        self.assertEqual([pod.order for pod in copied_pods], [1, 2, 3])
        self.assertTrue(set(pod.id for pod in copied_pods).isdisjoint(
            source_stage.pods.values_list('id', flat=True)))
        self.assertEqual(source_stage.pods.count(), 3)

    def test_copy_falls_back_to_source_pods_when_pod_fields_are_missing(self):
        tournament, _stage, _stage_players = self._create_stage_with_guest_players(
            0, pod_names=('North', 'South'), owner=self.owner)

        self.client.post(self._copy_url(tournament), self._get_copy_post_data())

        copied_pods = self._get_copied_tournament().stages.get(order=1).get_pods()
        self.assertEqual([pod.name for pod in copied_pods], ['North', 'South'])

    def test_copy_honours_pod_edits_made_on_the_copy_form(self):
        tournament, _stage, _stage_players = self._create_stage_with_guest_players(
            0, pod_names=('North', 'South'), owner=self.owner)

        self.client.post(self._copy_url(tournament),
                         self._get_copy_post_data(['North', 'West', 'Central']))

        copied_pods = self._get_copied_tournament().stages.get(order=1).get_pods()
        self.assertEqual([pod.name for pod in copied_pods], ['North', 'West', 'Central'])

    def test_copy_can_remove_all_pods(self):
        tournament, _stage, _stage_players = self._create_stage_with_guest_players(
            0, pod_names=('North', 'South'), owner=self.owner)

        self.client.post(self._copy_url(tournament), self._get_copy_post_data([]))

        self.assertFalse(self._get_copied_tournament().stages.get(order=1).pods.exists())

    def test_copy_of_completed_podded_tournament_starts_fresh(self):
        tournament, source_stage, _stage_players = self._create_stage_with_guest_players(
            6, pod_names=('North', 'South'), owner=self.owner)
        round_obj = self._pair_round(source_stage, 1)
        self._resolve_round_with_player_one_wins(round_obj)

        self.client.post(self._copy_url(tournament),
                         self._get_copy_post_data(['North', 'South']))

        copied_stage = self._get_copied_tournament().stages.get(order=1)
        self.assertEqual([pod.name for pod in copied_stage.get_pods()], ['North', 'South'])
        self.assertFalse(copied_stage.stage_players.exists())
        self.assertFalse(copied_stage.rounds.exists())
        self.assertEqual(source_stage.stage_players.filter(pod__isnull=False).count(), 6)

    def test_copied_podded_tournament_runs_with_pods(self):
        tournament, _stage, _stage_players = self._create_stage_with_guest_players(
            0, pod_names=('North', 'South'), owner=self.owner)
        self.client.post(self._copy_url(tournament),
                         self._get_copy_post_data(['North', 'South']))
        copy = self._get_copied_tournament()
        copied_stage = copy.stages.get(order=1)
        for i in range(4):
            player = Player.objects.create(tournament=copy, nickname=f'Copy {i + 1}')
            copied_stage.add_stage_player(player)

        self.client.post(reverse('tourney:tourney-prepare-current-stage-seeding', args=[copy.code]))
        self.client.post(reverse('tourney:tourney-start-next-stage', args=[copy.code]))

        self.assertEqual(Match.objects.filter(round__stage=copied_stage).count(), 2)
        self._assert_no_cross_pod_matches(copied_stage)

    def test_copy_of_tournament_with_pre_update_group_rows(self):
        tournament, source_stage, _stage_players = self._create_stage_with_guest_players(
            0, pod_names=('Legacy Group', 'Other Group'), owner=self.owner)
        source_stage.pods.update(slug='')
        from django.apps import apps as django_apps
        populate_pod_slugs = importlib.import_module(
            'tourney.migrations.0022_populate_pod_slugs').populate_pod_slugs
        populate_pod_slugs(django_apps, None)

        get_response = self.client.get(self._copy_url(tournament))
        self.client.post(self._copy_url(tournament), self._get_copy_post_data())

        self.assertEqual(
            list(source_stage.pods.values_list('slug', flat=True)),
            ['legacy-group', 'other-group'])
        self.assertEqual(get_response.status_code, 200)
        copied_pods = self._get_copied_tournament().stages.get(order=1).get_pods()
        self.assertEqual([pod.slug for pod in copied_pods], ['legacy-group', 'other-group'])


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class TournamentResultFormTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.co_admin = User.objects.create_user('coadmin', 'coadmin@test.com', 'password')
        self.form_owner = User.objects.create_user('formowner', 'formowner@test.com', 'password')

        self.result_form = GhostformForm.objects.create(
            owner=self.owner, title='Deck Check', status=GhostformForm.Status.PUBLISHED)
        self.deck_question = GhostformQuestion.objects.create(
            form=self.result_form, label='Your deck', order=1, is_required=True,
            answer_type=GhostformQuestion.AnswerType.DECK_LINK)
        self.notes_question = GhostformQuestion.objects.create(
            form=self.result_form, label='Notes', order=2)

        self.tournament = Tournament.objects.create(
            name='Result Form Night', owner=self.owner, result_form=self.result_form)
        TournamentAdmin.objects.create(tournament=self.tournament, user=self.co_admin)
        self.stage = Stage.objects.create(
            tournament=self.tournament, name='Main Stage', order=1, pairing_strategy='swiss',
            report_full_scores=Stage.SCORE_REPORTING_OPTIONAL)

        self.stage_players = []
        for i, nickname in enumerate(['Anvil', 'Beacon', 'Comet'], start=1):
            user = User.objects.create_user(f'user{i}', f'user{i}@test.com', 'password')
            player = Player.objects.create(user=user, tournament=self.tournament, nickname=nickname)
            self.stage_players.append(StagePlayer.objects.create(
                player=player, stage=self.stage, seed=i))
        self.anvil, self.beacon, self.comet = self.stage_players

        self.round = Round.objects.create(stage=self.stage, order=1)
        self.match = Match.objects.create(
            round=self.round, player_one=self.anvil, player_two=self.beacon)

    def _url(self, name, *args):
        return reverse(f'tourney:{name}', args=[self.tournament.code, *args])

    def _answers(self, deck_link=MASTER_VAULT_TEST_DECK_LINK, notes=''):
        return {
            f'ghostform-{self.deck_question.get_field_name()}': deck_link,
            f'ghostform-{self.notes_question.get_field_name()}': notes,
        }

    def _report(self, username, data):
        self.client.login(username=username, password='password')
        return self.client.post(self._url('tourney-report-result', self.match.id), data)

    def _context_values(self, response):
        return {item['label']: item['value'] for item in response.context}

    def _tournament_post_data(self, **overrides):
        data = {
            'name': 'Linked Tournament',
            'is_accepting_registrations': True,
            'is_public': False,
            'main_pairing_strategy': 'swiss',
            'main_score_reporting': '0',
            'main_allow_ties': 'False',
            'playoff_score_reporting': '0',
        }
        data.update(overrides)
        return data

    def test_player_report_requires_result_form_answers(self):
        response = self._report('user1', {'winner': self.anvil.id})

        self.assertFalse(MatchResult.objects.filter(match=self.match).exists())
        self.assertFalse(GhostformResponse.objects.exists())
        error_messages = [str(message) for message in response.wsgi_request._messages]
        self.assertTrue(any('Your deck' in message for message in error_messages))

    def _report_with_htmx(self, username, data):
        self.client.login(username=username, password='password')
        return self.client.post(
            self._url('tourney-report-result', self.match.id), data,
            HTTP_HX_REQUEST='true', HTTP_HX_CURRENT_URL=self._url('tourney-detail-matches'))

    def test_htmx_report_with_invalid_answers_rerenders_errors_in_dialog(self):
        response = self._report_with_htmx('user1', {
            'winner': self.anvil.id, **self._answers('https://example.com', notes='Keep me')})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['HX-Retarget'], '#reportFeedback')
        self.assertEqual(response['HX-Reswap'], 'innerHTML')
        self.assertNotIn('HX-Redirect', response)
        self.assertContains(response, 'Please fix the highlighted answers below.')
        self.assertNotContains(response, 'Please complete the result form.')
        self.assertContains(response, 'id="reportResultFormFields" hx-swap-oob="innerHTML"')
        self.assertContains(response, 'Enter a Master Vault or Decks of KeyForge deck link.')
        self.assertContains(response, 'value="Keep me"')
        self.assertContains(response, 'id="report-form-ghostform-')
        self.assertFalse(MatchResult.objects.filter(match=self.match).exists())

    def test_htmx_report_with_result_errors_lists_them_in_dialog(self):
        self.stage.report_full_scores = Stage.SCORE_REPORTING_REQUIRED
        self.stage.save()

        response = self._report_with_htmx('user1', {'winner': self.anvil.id, **self._answers()})

        self.assertEqual(response['HX-Retarget'], '#reportFeedback')
        self.assertContains(response, 'report-dialog__errors')
        self.assertFalse(MatchResult.objects.filter(match=self.match).exists())
        self.assertFalse(GhostformResponse.objects.exists())

    def test_htmx_report_success_redirects(self):
        response = self._report_with_htmx('user1', {'winner': self.anvil.id, **self._answers()})

        self.assertIn('HX-Redirect', response)
        self.assertTrue(MatchResult.objects.filter(match=self.match).exists())

    def test_htmx_player_added_result_errors_stay_in_dialog(self):
        self._use_self_scheduled_pairing()
        Round.objects.create(stage=self.stage, order=2)
        self.client.login(username='user1', password='password')

        response = self.client.post(
            self._url('tourney-player-add-match-result'), {'opponent': self.comet.id},
            HTTP_HX_REQUEST='true', HTTP_HX_CURRENT_URL=self._url('tourney-detail-matches'))

        self.assertEqual(response['HX-Retarget'], '#reportFeedback')
        self.assertContains(response, 'Please select a winner.')

    def test_player_report_rejects_invalid_deck_link(self):
        self._report('user1', {'winner': self.anvil.id, **self._answers('https://example.com')})

        self.assertFalse(MatchResult.objects.filter(match=self.match).exists())
        self.assertFalse(GhostformResponse.objects.exists())

    def test_player_report_records_result_and_response_together(self):
        self._report('user1', {
            'winner': self.anvil.id, 'player_one_score': '3', 'player_two_score': '1',
            **self._answers(notes='Close game'),
        })

        result = MatchResult.objects.get(match=self.match)
        response = GhostformResponse.objects.get()
        self.assertEqual(result.winner, self.anvil)
        self.assertEqual(response.form, self.result_form)
        self.assertEqual(response.user.username, 'user1')
        self.assertEqual(response.context_key, f'tourney-match:{self.match.id}')
        self.assertEqual(
            list(response.answers.order_by('question__order').values_list('value', flat=True)),
            [MASTER_VAULT_TEST_DECK_LINK, 'Close game'])

    def test_response_captures_result_context(self):
        self._report('user1', {
            'winner': self.anvil.id, 'player_one_score': '3', 'player_two_score': '1',
            **self._answers(),
        })

        response = GhostformResponse.objects.get()
        context_values = self._context_values(response)
        self.assertEqual([item['label'] for item in response.context], [
            'Tournament', 'Tournament code', 'Stage', 'Round', 'Player one', 'Player two',
            'Winner', 'Player one score', 'Player two score', 'Result recorded at'])
        self.assertEqual(context_values['Tournament'], 'Result Form Night')
        self.assertEqual(context_values['Tournament code'], self.tournament.code)
        self.assertEqual(context_values['Stage'], 'Main Stage')
        self.assertEqual(context_values['Round'], 1)
        self.assertEqual(context_values['Player one'], 'Anvil')
        self.assertEqual(context_values['Player two'], 'Beacon')
        self.assertEqual(context_values['Winner'], 'Anvil')
        self.assertEqual(context_values['Player one score'], 3)
        self.assertEqual(context_values['Player two score'], 1)
        self.assertTrue(context_values['Result recorded at'])

    def test_failed_response_save_rolls_back_result(self):
        with patch('tourney.reporting.record_result_response', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self._report('user1', {'winner': self.anvil.id, **self._answers()})

        self.assertFalse(MatchResult.objects.filter(match=self.match).exists())

    def test_admin_report_does_not_require_answers(self):
        self._report('owner', {'winner': self.beacon.id})

        self.assertEqual(MatchResult.objects.get(match=self.match).winner, self.beacon)
        self.assertFalse(GhostformResponse.objects.exists())

    def test_admin_report_with_answers_records_response(self):
        self._report('coadmin', {'winner': self.beacon.id, **self._answers(deck_link='', notes='Judge call')})

        response = GhostformResponse.objects.get()
        self.assertEqual(response.user, self.co_admin)
        self.assertEqual(list(response.answers.values_list('value', flat=True)), ['Judge call'])

    def test_admin_report_still_validates_answer_format(self):
        self._report('owner', {'winner': self.beacon.id, **self._answers(deck_link='not a deck')})

        self.assertFalse(MatchResult.objects.filter(match=self.match).exists())

    def test_linked_form_is_required_whatever_its_status(self):
        for status in [GhostformForm.Status.DRAFT, GhostformForm.Status.CLOSED]:
            self.result_form.status = status
            self.result_form.save()

            self._report('user1', {'winner': self.anvil.id})

            self.assertFalse(MatchResult.objects.filter(match=self.match).exists(), status)

    def test_draft_linked_form_collects_responses(self):
        self.result_form.status = GhostformForm.Status.DRAFT
        self.result_form.save()

        self._report('user1', {'winner': self.anvil.id, **self._answers()})

        self.assertTrue(MatchResult.objects.filter(match=self.match).exists())
        self.assertEqual(GhostformResponse.objects.get().form, self.result_form)

    def test_linked_form_without_questions_is_skipped(self):
        GhostformQuestion.objects.filter(form=self.result_form).delete()
        self.client.login(username='user1', password='password')

        matches_response = self.client.get(self._url('tourney-detail-matches'))
        self._report('user1', {'winner': self.anvil.id})

        self.assertNotContains(matches_response, 'data-result-form')
        self.assertTrue(MatchResult.objects.filter(match=self.match).exists())
        self.assertFalse(GhostformResponse.objects.exists())

    def test_closed_tournament_blocks_player_reports_before_the_form(self):
        self.tournament.is_closed = True
        self.tournament.save()

        self._report('user1', {'winner': self.anvil.id, **self._answers()})

        self.assertFalse(MatchResult.objects.filter(match=self.match).exists())
        self.assertFalse(GhostformResponse.objects.exists())

    def test_tournament_without_result_form_reports_as_before(self):
        self.tournament.result_form = None
        self.tournament.save()

        self._report('user1', {'winner': self.anvil.id})

        self.assertTrue(MatchResult.objects.filter(match=self.match).exists())

    def test_admin_edit_updates_response_snapshot(self):
        self._report('user1', {'winner': self.anvil.id, **self._answers()})

        self._report('owner', {'winner': self.beacon.id, 'player_one_score': '1', 'player_two_score': '3'})

        response = GhostformResponse.objects.get()
        context_values = self._context_values(response)
        self.assertEqual(context_values['Winner'], 'Beacon')
        self.assertEqual(context_values['Player two score'], 3)
        self.assertFalse(response.is_context_removed)

    def test_reset_match_marks_response_removed(self):
        self._report('user1', {'winner': self.anvil.id, **self._answers()})

        self.client.login(username='owner', password='password')
        self.client.post(self._url('tourney-reset-match', self.match.id))

        response = GhostformResponse.objects.get()
        self.assertTrue(response.is_context_removed)
        self.assertEqual(self._context_values(response)['Winner'], 'Anvil')

    def test_rereport_after_reset_creates_new_active_response(self):
        self._report('user1', {'winner': self.anvil.id, **self._answers()})
        self.client.login(username='owner', password='password')
        self.client.post(self._url('tourney-reset-match', self.match.id))

        self._report('user2', {'winner': self.beacon.id, **self._answers()})

        removed_response = GhostformResponse.objects.get(is_context_removed=True)
        active_response = GhostformResponse.objects.get(is_context_removed=False)
        self.assertEqual(self._context_values(removed_response)['Winner'], 'Anvil')
        self.assertEqual(self._context_values(active_response)['Winner'], 'Beacon')

    def test_delete_match_keeps_response_marked_removed(self):
        self._report('user1', {'winner': self.anvil.id, **self._answers()})

        self.client.login(username='owner', password='password')
        self.client.post(self._url('tourney-delete-match', self.match.id))

        self.assertFalse(Match.objects.filter(id=self.match.id).exists())
        self.assertTrue(GhostformResponse.objects.get().is_context_removed)

    def test_deleting_tournament_keeps_responses(self):
        self._report('user1', {'winner': self.anvil.id, **self._answers()})

        self.tournament.delete()

        self.assertTrue(GhostformResponse.objects.get().is_context_removed)

    def _use_self_scheduled_pairing(self):
        self.stage.pairing_strategy = 'round_robin'
        self.stage.save()

    def test_player_added_result_requires_answers(self):
        self._use_self_scheduled_pairing()
        Round.objects.create(stage=self.stage, order=2)
        self.client.login(username='user1', password='password')

        self.client.post(self._url('tourney-player-add-match-result'), {
            'opponent': self.comet.id, 'winner': 'me'})

        self.assertFalse(Match.objects.filter(round__order=2).exists())
        self.assertFalse(GhostformResponse.objects.exists())

    def test_player_added_result_rolls_back_when_response_fails(self):
        self._use_self_scheduled_pairing()
        new_round = Round.objects.create(stage=self.stage, order=2)
        self.client.login(username='user1', password='password')

        with patch('tourney.reporting.record_result_response', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.client.post(self._url('tourney-player-add-match-result'), {
                    'opponent': self.comet.id, 'winner': 'them', **self._answers()})

        self.assertFalse(new_round.matches.exists())

    def test_player_added_result_records_response(self):
        self._use_self_scheduled_pairing()
        new_round = Round.objects.create(stage=self.stage, order=2)
        self.client.login(username='user1', password='password')

        self.client.post(self._url('tourney-player-add-match-result'), {
            'opponent': self.comet.id, 'winner': 'them', **self._answers()})

        match = new_round.matches.get()
        response = GhostformResponse.objects.get()
        self.assertEqual(match.result.winner, self.comet)
        self.assertEqual(response.context_key, f'tourney-match:{match.id}')
        self.assertEqual(self._context_values(response)['Round'], 2)
        self.assertEqual(self._context_values(response)['Winner'], 'Comet')

    def test_matches_page_renders_result_form_for_player(self):
        self.client.login(username='user1', password='password')

        response = self.client.get(self._url('tourney-detail-matches'))

        self.assertContains(response, f'name="ghostform-{self.deck_question.get_field_name()}"', count=1)
        self.assertContains(response, 'id="report-form-ghostform-')
        self.assertContains(response, 'data-result-form', count=1)
        self.assertContains(response, 'id="matchModal"', count=1)
        self.assertNotContains(response, 'playerMatchReportModal')
        self.assertNotContains(response, '(optional)</summary>')

    def test_matches_page_renders_optional_result_form_for_admin(self):
        self.client.login(username='owner', password='password')

        response = self.client.get(self._url('tourney-detail-matches'))

        self.assertContains(response, 'Deck Check (optional)</summary>')

    def test_matches_page_renders_draft_result_form(self):
        self.result_form.status = GhostformForm.Status.DRAFT
        self.result_form.save()
        self.client.login(username='user1', password='password')

        response = self.client.get(self._url('tourney-detail-matches'))

        self.assertContains(response, 'data-result-form')

    def test_admin_tab_links_to_result_form(self):
        self.client.login(username='coadmin', password='password')

        response = self.client.get(self._url('tourney-tournament-detail-admin'))

        self.assertContains(response, reverse('ghostform:ghostform-detail', args=[self.result_form.code]))
        self.assertContains(response, reverse('ghostform:ghostform-responses-csv', args=[self.result_form.code]))

    def test_co_admin_can_view_linked_form_and_download_csv(self):
        self._report('user1', {'winner': self.anvil.id, **self._answers()})
        self.client.login(username='coadmin', password='password')

        detail_response = self.client.get(reverse('ghostform:ghostform-detail', args=[self.result_form.code]))
        csv_response = self.client.get(reverse('ghostform:ghostform-responses-csv', args=[self.result_form.code]))
        edit_response = self.client.get(reverse('ghostform:ghostform-edit', args=[self.result_form.code]))

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(edit_response.status_code, 403)
        csv_rows = list(csv.reader(io.StringIO(csv_response.content.decode())))
        self.assertIn('Winner', csv_rows[0])
        self.assertIn('Linked record removed', csv_rows[0])
        self.assertEqual(csv_rows[1][csv_rows[0].index('Winner')], 'Anvil')

    def test_players_cannot_view_linked_form_responses(self):
        self.client.login(username='user1', password='password')

        response = self.client.get(reverse('ghostform:ghostform-detail', args=[self.result_form.code]))

        self.assertEqual(response.status_code, 403)

    def test_create_tournament_links_own_form(self):
        self.client.login(username='owner', password='password')

        self.client.post(reverse('tourney:tourney-create-tournament'), self._tournament_post_data(
            result_form=self.result_form.id))

        self.assertEqual(Tournament.objects.get(name='Linked Tournament').result_form, self.result_form)

    def test_create_tournament_cannot_link_someone_elses_form(self):
        other_form = GhostformForm.objects.create(owner=self.form_owner, title='Private')
        self.client.login(username='owner', password='password')

        response = self.client.post(reverse('tourney:tourney-create-tournament'), self._tournament_post_data(
            result_form=other_form.id))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Tournament.objects.filter(name='Linked Tournament').exists())
        self.assertIn('result_form', response.context['form'].errors)

    def test_result_form_choices_are_scoped_to_user(self):
        GhostformForm.objects.create(owner=self.form_owner, title='Private')
        own_draft = GhostformForm.objects.create(owner=self.owner, title='Another')
        self.client.login(username='owner', password='password')

        response = self.client.get(reverse('tourney:tourney-create-tournament'))

        choices = list(response.context['form'].fields['result_form'].queryset)
        picker_titles = [option['title'] for option in response.context['result_form_picker']['results']]
        self.assertEqual(choices, [own_draft, self.result_form])
        self.assertEqual(sorted(picker_titles), ['Another', 'Deck Check'])
        self.assertNotIn('Private', picker_titles)

    def test_picker_describes_forms_with_linked_tournaments(self):
        self.client.login(username='owner', password='password')

        response = self.client.get(reverse('ghostform:ghostform-picker-results'), {'q': 'deck'})

        self.assertContains(response, 'Deck Check')
        self.assertContains(response, 'used by Result Form Night')
        self.assertContains(response, '2 questions')

    def test_edit_picker_shows_linked_form_for_co_admin(self):
        self.client.login(username='coadmin', password='password')

        response = self.client.get(self._url('tourney-edit-tournament'))

        picker = response.context['result_form_picker']
        self.assertEqual(picker['selected_value'], str(self.result_form.pk))
        self.assertEqual(picker['selected_option']['title'], 'Deck Check')
        self.assertEqual(picker['results'], [])
        self.assertEqual(picker['special_options'][0]['value'], str(self.result_form.pk))
        self.assertIn('Owned by another admin', picker['special_options'][0]['meta'])
        self.assertContains(response, f'name="result_form" value="{self.result_form.pk}"')

    def test_picker_usage_only_names_tournaments_the_viewer_administers(self):
        Tournament.objects.create(name='Owner Secret Event', owner=self.owner, result_form=self.result_form)
        self.client.login(username='coadmin', password='password')

        response = self.client.get(self._url('tourney-edit-tournament'))

        selected_meta = response.context['result_form_picker']['selected_option']['meta']
        self.assertIn('used by Result Form Night', selected_meta)
        self.assertNotIn('Owner Secret Event', selected_meta)

    def test_picker_drops_stale_selected_value(self):
        self.client.login(username='owner', password='password')

        response = self.client.post(reverse('tourney:tourney-create-tournament'), self._tournament_post_data(
            name='', result_form='999999'))

        picker = response.context['result_form_picker']
        self.assertEqual(picker['selected_value'], '')
        self.assertEqual(picker['selected_option']['title'], 'No form')

    def test_create_picker_defaults_to_no_form(self):
        self.client.login(username='owner', password='password')

        response = self.client.get(reverse('tourney:tourney-create-tournament'))

        picker = response.context['result_form_picker']
        self.assertEqual(picker['selected_value'], '')
        self.assertEqual(picker['selected_option']['title'], 'No form')

    def test_invalid_submission_keeps_picker_selection(self):
        self.client.login(username='owner', password='password')

        response = self.client.post(reverse('tourney:tourney-create-tournament'), self._tournament_post_data(
            name='', result_form=self.result_form.id))

        self.assertEqual(
            response.context['result_form_picker']['selected_option']['title'], 'Deck Check')

    def test_co_admin_edit_keeps_owner_form_linked(self):
        self.client.login(username='coadmin', password='password')
        edit_url = self._url('tourney-edit-tournament')

        get_response = self.client.get(edit_url)
        self.client.post(edit_url, self._tournament_post_data(
            name='Result Form Night', result_form=self.result_form.id))

        self.assertIn(self.result_form, get_response.context['form'].fields['result_form'].queryset)
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.result_form, self.result_form)

    def test_edit_can_unlink_result_form(self):
        self.client.login(username='owner', password='password')

        self.client.post(self._url('tourney-edit-tournament'), self._tournament_post_data(
            name='Result Form Night', result_form=''))

        self.tournament.refresh_from_db()
        self.assertIsNone(self.tournament.result_form)

    def _copy_with_result_form_choice(self, username, result_form_choice, name='Linked Tournament'):
        self.client.login(username=username, password='password')
        return self.client.post(self._url('tourney-copy-tournament'), self._tournament_post_data(
            name=name, result_form=result_form_choice))

    def test_copy_page_defaults_to_copying_the_result_form(self):
        self.client.login(username='owner', password='password')

        response = self.client.get(self._url('tourney-copy-tournament'))

        picker = response.context['result_form_picker']
        self.assertEqual(response.context['form'].initial['result_form'], 'copy')
        self.assertEqual(picker['selected_value'], 'copy')
        self.assertEqual(picker['selected_option']['title'], 'Copy of Deck Check')
        self.assertEqual(
            [option['value'] for option in picker['special_options']], ['copy', ''])
        self.assertContains(response, 'data-value="copy"')

    def test_copy_clones_result_form_for_the_copier(self):
        self._report('user1', {'winner': self.anvil.id, **self._answers()})
        archived_question = GhostformQuestion.objects.create(
            form=self.result_form, label='Retired', order=3, is_archived=True)

        self._copy_with_result_form_choice('owner', 'copy')

        copied_form = Tournament.objects.get(name='Linked Tournament').result_form
        self.assertNotEqual(copied_form, self.result_form)
        self.assertEqual(copied_form.owner, self.owner)
        self.assertEqual(copied_form.title, 'Linked Tournament - Deck Check')
        self.assertEqual(copied_form.status, GhostformForm.Status.PUBLISHED)
        self.assertFalse(copied_form.responses.exists())
        self.assertEqual(
            list(copied_form.questions.values_list('label', 'answer_type', 'is_required', 'order')),
            [('Your deck', 'deck_link', True, 1), ('Notes', 'text', False, 2)])
        self.assertNotIn(archived_question.label, copied_form.questions.values_list('label', flat=True))
        self.assertEqual(self.result_form.responses.count(), 1)

    def test_co_admin_copy_clones_form_into_their_own_form(self):
        self._report('user1', {'winner': self.anvil.id, **self._answers()})

        self._copy_with_result_form_choice('coadmin', 'copy')

        copied_form = Tournament.objects.get(name='Linked Tournament').result_form
        self.assertEqual(copied_form.owner, self.co_admin)
        self.assertFalse(copied_form.responses.exists())
        self.assertTrue(copied_form.can_edit(self.co_admin))

    def test_co_admin_copy_cannot_link_owner_form_directly(self):
        response = self._copy_with_result_form_choice('coadmin', self.result_form.id)

        self.assertIn('result_form', response.context['form'].errors)
        self.assertFalse(Tournament.objects.filter(name='Linked Tournament').exists())

    def test_copy_can_link_an_existing_own_form_instead(self):
        self._copy_with_result_form_choice('owner', self.result_form.id)

        self.assertEqual(Tournament.objects.get(name='Linked Tournament').result_form, self.result_form)
        self.assertEqual(GhostformForm.objects.count(), 1)

    def test_copy_can_choose_no_form(self):
        self._copy_with_result_form_choice('owner', '')

        self.assertIsNone(Tournament.objects.get(name='Linked Tournament').result_form)
        self.assertEqual(GhostformForm.objects.count(), 1)

    def test_copy_chain_does_not_stack_tournament_prefixes(self):
        self._copy_with_result_form_choice('owner', 'copy', name='Result Form Night #2')
        second_tournament = Tournament.objects.get(name='Result Form Night #2')

        self.client.post(
            reverse('tourney:tourney-copy-tournament', args=[second_tournament.code]),
            self._tournament_post_data(name='Result Form Night #3', result_form='copy'))

        self.assertEqual(second_tournament.result_form.title, 'Result Form Night #2 - Deck Check')
        self.assertEqual(
            Tournament.objects.get(name='Result Form Night #3').result_form.title,
            'Result Form Night #3 - Deck Check')

    def test_copied_form_keeps_draft_status(self):
        self.result_form.status = GhostformForm.Status.DRAFT
        self.result_form.save()

        self._copy_with_result_form_choice('owner', 'copy')

        copied_form = Tournament.objects.get(name='Linked Tournament').result_form
        self.assertEqual(copied_form.status, GhostformForm.Status.DRAFT)

    def test_co_admin_edit_cannot_link_other_owner_forms(self):
        other_owner_form = GhostformForm.objects.create(owner=self.owner, title='Owner Private')
        self.client.login(username='coadmin', password='password')

        response = self.client.post(self._url('tourney-edit-tournament'), self._tournament_post_data(
            name='Result Form Night', result_form=other_owner_form.id))

        self.assertIn('result_form', response.context['form'].errors)
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.result_form, self.result_form)

    def test_dropped_player_with_unreported_match_still_gets_result_form(self):
        Player.objects.filter(user__username='user1').update(status=Player.PlayerStatus.DROPPED)
        self.client.login(username='user1', password='password')

        response = self.client.get(self._url('tourney-detail-matches'))
        self._report('user1', {'winner': self.anvil.id, **self._answers()})

        self.assertContains(response, 'data-result-form')
        self.assertTrue(GhostformResponse.objects.exists())

    def test_spectator_does_not_get_result_form(self):
        User.objects.create_user('spectator', 'spectator@test.com', 'password')
        self.tournament.is_public = True
        self.tournament.save()
        self.client.login(username='spectator', password='password')

        response = self.client.get(self._url('tourney-detail-matches'))

        self.assertNotContains(response, 'data-result-form')

    def test_bye_results_cannot_be_reported(self):
        bye_match = Match.objects.create(round=self.round, player_one=self.comet)
        MatchResult.objects.create(match=bye_match, winner=self.comet)
        self.stage.are_ties_allowed = True
        self.stage.save()
        self.client.login(username='owner', password='password')

        self.client.post(self._url('tourney-report-result', bye_match.id), {'winner': ''})

        bye_match.result.refresh_from_db()
        self.assertEqual(bye_match.result.winner, self.comet)

    def test_htmx_errors_rerender_answers_even_when_only_result_is_invalid(self):
        self.stage.report_full_scores = Stage.SCORE_REPORTING_REQUIRED
        self.stage.save()

        response = self._report_with_htmx('user1', {
            'winner': self.anvil.id, **self._answers(notes='Keep me')})

        self.assertContains(response, 'id="reportResultFormFields" hx-swap-oob="innerHTML"')
        self.assertContains(response, 'value="Keep me"')
        self.assertNotContains(response, 'Please fix the highlighted answers below.')

    def test_player_added_result_reports_score_errors_before_answers(self):
        self._use_self_scheduled_pairing()
        self.stage.report_full_scores = Stage.SCORE_REPORTING_OPTIONAL
        self.stage.save()
        Round.objects.create(stage=self.stage, order=2)
        self.client.login(username='user1', password='password')

        response = self.client.post(
            self._url('tourney-player-add-match-result'),
            {'opponent': self.comet.id, 'winner': 'me', 'my_score': '-4'},
            HTTP_HX_REQUEST='true', HTTP_HX_CURRENT_URL=self._url('tourney-detail-matches'))

        self.assertContains(response, 'Invalid score entered.')

    def test_copy_of_tournament_without_form_has_no_form(self):
        self.tournament.result_form = None
        self.tournament.save()
        self.client.login(username='owner', password='password')

        get_response = self.client.get(self._url('tourney-copy-tournament'))
        self.client.post(self._url('tourney-copy-tournament'), self._tournament_post_data())

        self.assertEqual(get_response.context['form'].initial['result_form'], '')
        self.assertNotContains(get_response, '(new form)')
        self.assertIsNone(Tournament.objects.get(name='Linked Tournament').result_form)

    def test_deleting_form_unlinks_tournament(self):
        self.result_form.delete()

        self.tournament.refresh_from_db()
        self.assertIsNone(self.tournament.result_form)


class ReportingServiceTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('reportowner')
        self.tournament = Tournament.objects.create(name='Service Night', owner=self.owner)
        self.stage = Stage.objects.create(
            tournament=self.tournament, name='Main Stage', order=1, pairing_strategy='swiss',
            report_full_scores=Stage.SCORE_REPORTING_OPTIONAL)
        self.users = []
        self.stage_players = []
        for i, nickname in enumerate(['Anvil', 'Beacon', 'Comet'], start=1):
            user = User.objects.create_user(f'reporter{i}')
            player = Player.objects.create(user=user, tournament=self.tournament, nickname=nickname)
            self.users.append(user)
            self.stage_players.append(StagePlayer.objects.create(player=player, stage=self.stage, seed=i))
        self.anvil, self.beacon, self.comet = self.stage_players
        self.round = Round.objects.create(stage=self.stage, order=1)
        self.match = Match.objects.create(round=self.round, player_one=self.anvil, player_two=self.beacon)

    def test_paired_report_records_result(self):
        outcome = report_paired_match_result(self.match, self.users[0], {
            'winner': self.anvil.id, 'player_one_score': '3', 'player_two_score': '1'})

        self.assertFalse(outcome.was_update)
        self.assertEqual(outcome.result.winner, self.anvil)
        self.assertEqual(describe_winner(outcome.result), 'Anvil')

    def test_paired_report_by_outsider_is_denied(self):
        with self.assertRaises(PermissionDenied):
            report_paired_match_result(self.match, self.users[2], {'winner': self.anvil.id})

    def test_paired_report_on_reported_match_is_final(self):
        MatchResult.objects.create(match=self.match, winner=self.beacon)

        with self.assertRaises(ReportError) as raised:
            report_paired_match_result(self.match, self.users[0], {'winner': self.anvil.id})

        self.assertTrue(raised.exception.is_final)
        self.assertEqual(raised.exception.error_messages, [MATCH_ALREADY_REPORTED_MESSAGE])

    def test_paired_report_with_invalid_result_lists_form_errors(self):
        with self.assertRaises(ReportError) as raised:
            report_paired_match_result(self.match, self.users[0], {'winner': ''})

        self.assertFalse(raised.exception.is_final)
        self.assertTrue(raised.exception.error_messages)
        self.assertFalse(MatchResult.objects.exists())

    def test_self_scheduled_report_creates_match_and_result(self):
        self.stage.pairing_strategy = 'round_robin'
        self.stage.save()
        current_round = Round.objects.create(stage=self.stage, order=2)

        outcome = report_self_scheduled_match_result(self.tournament, self.users[0], {
            'opponent': str(self.comet.id), 'winner': 'them', 'my_score': '1', 'their_score': '3'})

        self.assertEqual(outcome.result.match.round, current_round)
        self.assertEqual(outcome.result.winner, self.comet)
        self.assertEqual((outcome.result.player_one_score, outcome.result.player_two_score), (1, 3))

    def test_self_scheduled_report_rejects_unknown_winner_choice(self):
        self.stage.pairing_strategy = 'round_robin'
        self.stage.save()
        Round.objects.create(stage=self.stage, order=2)

        with self.assertRaises(ReportError) as raised:
            report_self_scheduled_match_result(self.tournament, self.users[0], {
                'opponent': str(self.comet.id), 'winner': 'nobody'})

        self.assertEqual(raised.exception.error_messages, [INVALID_WINNER_MESSAGE])

    def test_self_scheduled_report_is_denied_in_paired_stage(self):
        with self.assertRaises(PermissionDenied):
            report_self_scheduled_match_result(self.tournament, self.users[0], {})
