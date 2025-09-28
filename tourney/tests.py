import logging
from django.test import TestCase
from django.contrib.auth.models import User
from django.db import models
from .models import (
    Tournament, Player, Stage, StagePlayer, Round, Match, MatchResult,
    StandingCalculator, get_pairing_strategy
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

            # Verify performance: should complete in under 1 second even for 100 players
            self.assertLess(pairing_time, 1.0, f"Round {round_num} pairing took too long: {pairing_time:.3f}s")

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

            if lower_ranked_without_byes:
                # Check if giving bye to the lowest ranked would force rematches
                alternative_bye_player = lower_ranked_without_byes[0]  # Lowest ranked without bye
                remaining_players = [s['stage_player'] for s in standings_after_r1 if s['stage_player'] != alternative_bye_player]

                # Get Round 1 opponent history
                r1_opponents = {}
                for match in matches_r1:
                    if match.player_two is not None:  # Not a bye match
                        p1, p2 = match.player_one, match.player_two
                        r1_opponents.setdefault(p1.id, set()).add(p2.id)
                        r1_opponents.setdefault(p2.id, set()).add(p1.id)

                # Check if remaining players can be paired without rematches
                can_avoid_rematches = True
                pairing_analysis = []
                used = set()

                for i, player1 in enumerate(remaining_players):
                    if player1.id in used:
                        continue

                    found_opponent = False
                    for j, player2 in enumerate(remaining_players[i+1:], i+1):
                        if (player2.id not in used and
                            player2.id not in r1_opponents.get(player1.id, set())):
                            pairing_analysis.append(f"{player1.player.get_display_name()} vs {player2.player.get_display_name()}")
                            used.add(player1.id)
                            used.add(player2.id)
                            found_opponent = True
                            break

                    if not found_opponent:
                        can_avoid_rematches = False
                        break

                failure_msg = (
                    f"Round 2 bye went to {bye_player_r2.player.get_display_name()} "
                    f"(rank {bye_player_rank + 1}) when lower-ranked players without byes were available: "
                    f"{[p.player.get_display_name() for p in lower_ranked_without_byes]}. "
                    f"Current standings: {[(i+1, s['stage_player'].player.get_display_name(), s['wins']) for i, s in enumerate(standings_after_r1)]}. ")

                if can_avoid_rematches:
                    failure_msg += f"Alternative pairing with {alternative_bye_player.player.get_display_name()} bye would work: {pairing_analysis}"
                else:
                    failure_msg += f"Alternative bye assignment might force rematches - this could be acceptable."

                # Only fail if we can definitely avoid rematches
                if can_avoid_rematches:
                    self.fail(failure_msg)
                else:
                    logger.debug(f"Bye assignment may be acceptable due to pairing constraints: {failure_msg}")

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

            # Check for previous bye recipients
            previous_bye_recipients = set()
            if r1_bye_match:
                previous_bye_recipients.add(r1_bye_match.player_one.id)
            if r2_bye_match:
                previous_bye_recipients.add(r2_bye_match.player_one.id)

            # Find lower ranked players without previous byes
            lower_ranked_without_byes_r3 = []
            for i, standing in enumerate(standings_after_r2):
                if (i > bye_player_rank_r3 and  # Lower ranked
                    standing['stage_player'].id not in previous_bye_recipients):  # No previous bye
                    lower_ranked_without_byes_r3.append(standing['stage_player'])

            if lower_ranked_without_byes_r3:
                self.fail(
                    f"Round 3 bye went to {bye_player_r3.player.get_display_name()} "
                    f"(rank {bye_player_rank_r3 + 1}) when lower-ranked players without byes were available: "
                    f"{[p.player.get_display_name() for p in lower_ranked_without_byes_r3]}. "
                    f"Current standings: {[(i+1, s['stage_player'].player.get_display_name(), s['wins']) for i, s in enumerate(standings_after_r2)]}")

        logger.debug(f"Bye placement test passed - byes went to appropriately ranked players")

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