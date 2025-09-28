"""
Round Robin Scheduled Pairing Strategy

A round robin tournament strategy where all rounds and matches are created
in advance, ensuring each player plays every other player exactly once.
"""

from .base import PairingStrategy


class RoundRobinScheduledPairingStrategy(PairingStrategy):
    """
    Round robin scheduled pairing strategy implementation.

    In round robin scheduled:
    - All rounds are created when the first round is created
    - All matches are generated to ensure each player plays every other player once
    - No additional rounds can be created beyond the initial set
    - Uses round-robin algorithm to distribute matches across rounds
    """

    name = "round_robin_scheduled"
    display_name = "Round Robin"
    description = "All rounds and matches created in advance, each player plays every other player once"

    def make_pairings_for_round(self, round_obj):
        """
        Generate all rounds and matches for the round robin tournament.
        This is only called for the first round - all subsequent rounds and matches
        are created at the same time.
        """
        from tourney.models import Player, Match, Round

        stage = round_obj.stage
        stage_players = list(stage.stage_players.filter(
            player__status=Player.PlayerStatus.ACTIVE))

        if len(stage_players) < 2:
            return

        # Only generate if this is the first round
        if round_obj.order != 1:
            return

        # Generate round robin schedule
        schedule = self._generate_round_robin_schedule(stage_players)

        # Create all rounds and matches
        matches_to_create = []

        for round_number, round_matches in enumerate(schedule, 1):
            if round_number == 1:
                # Use the existing round
                target_round = round_obj
            else:
                # Create new rounds
                target_round = Round.objects.create(
                    stage=stage,
                    order=round_number
                )

            # Create matches for this round
            for player_one, player_two in round_matches:
                match = Match(
                    round=target_round,
                    player_one=player_one,
                    player_two=player_two
                )
                matches_to_create.append(match)

        # Bulk create all matches
        if matches_to_create:
            Match.objects.bulk_create(matches_to_create)

    def _generate_round_robin_schedule(self, players):
        """
        Generate a round robin schedule where each player plays every other player exactly once.

        Uses the polygon method (circle rotation algorithm):
        - Fix one player at the top, rotate others clockwise
        - Each round, pair players across the circle

        Args:
            players: List of stage players

        Returns:
            List of rounds, where each round is a list of (player1, player2) tuples
        """
        if len(players) < 2:
            return []

        # Make a copy to avoid modifying the original list
        players_list = list(players)

        # Handle odd number of players by adding None (bye)
        original_count = len(players_list)
        if len(players_list) % 2 == 1:
            players_list.append(None)

        num_players = len(players_list)
        num_rounds = num_players - 1

        schedule = []

        # Use the standard round-robin algorithm
        # Fix the first player, rotate the rest
        for round_num in range(num_rounds):
            round_matches = []

            # Create a list representing current round arrangement
            # Player 0 is fixed, others rotate
            current_arrangement = [players_list[0]]  # Fixed player

            # Add rotating players
            for i in range(1, num_players):
                idx = ((i - 1 - round_num) % (num_players - 1)) + 1
                current_arrangement.append(players_list[idx])

            # Pair players: 0 with last, 1 with second-to-last, etc.
            for i in range(num_players // 2):
                player1 = current_arrangement[i]
                player2 = current_arrangement[num_players - 1 - i]

                # Only add valid matches (not both None)
                if player1 is not None and player2 is not None:
                    round_matches.append((player1, player2))
                elif player1 is not None:
                    round_matches.append((player1, None))
                elif player2 is not None:
                    round_matches.append((player2, None))

            if round_matches:
                schedule.append(round_matches)

        return schedule

    def can_create_new_round(self, stage):
        """
        Prevent creation of additional rounds beyond the initial set.
        All rounds are created when the tournament starts.

        Args:
            stage: The tournament stage

        Returns:
            bool: False - no additional rounds can be created
        """
        return False

    def is_self_scheduled(self):
        return False

    def is_elimination_style(self):
        return False
