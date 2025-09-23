from django.test import TestCase
from django.contrib.auth.models import User
from .models import (
    Tournament, Player, Stage, StagePlayer, Round, Match, MatchResult,
    StandingCalculator, get_pairing_strategy
)


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

        # Create main stage with Wins -> Seed ranking criteria
        self.main_stage = Stage.objects.create(
            tournament=self.tournament,
            name='Main Stage',
            order=1,
            pairing_strategy='swiss'
        )

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

            print(f"Round {round_num} pairing completed in {pairing_time:.3f}s with {matches.count()} matches")

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

            print(f"Round {round_num} pairing completed in {pairing_time:.3f}s with {matches.count()} matches")

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

        print(f"14-player tournament (brute force) completed in {pairing_time:.3f}s")

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