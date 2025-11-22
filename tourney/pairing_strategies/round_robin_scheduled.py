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
    - All rounds are typically created when the first round is created
    - All matches are generated to ensure each player plays every other player once
    - Additional rounds can be created if there are unmatched pairs remaining
    - Uses round-robin algorithm to distribute matches optimally across rounds
    """

    name = "round_robin_scheduled"
    display_name = "Round Robin"
    description = "Round robin tournament where each player plays every other player once"

    def make_pairings_for_round(self, round_obj):
        """
        Generate matches for the round robin tournament.

        For the first round, all rounds and matches are created upfront.
        For subsequent rounds (when new rounds are added dynamically),
        generates the minimum number of rounds needed to complete the
        round robin with all remaining unmatched pairs.
        """
        from tourney.models import Player, Match, Round

        stage = round_obj.stage
        stage_players = list(stage.stage_players.filter(
            player__status=Player.PlayerStatus.ACTIVE))

        if len(stage_players) < 2:
            return

        if round_obj.order == 1:
            schedule = self._generate_round_robin_schedule(stage_players)
        else:
            existing_pairings = self._get_existing_pairings(stage)
            schedule = self._generate_remaining_schedule(
                stage_players, existing_pairings)

        if not schedule:
            return

        matches_to_create = []

        for round_number, round_matches in enumerate(schedule, round_obj.order):
            if round_number == round_obj.order:
                target_round = round_obj
            else:
                target_round = Round.objects.create(
                    stage=stage,
                    order=round_number
                )

            for player_one, player_two in round_matches:
                match = Match(
                    round=target_round,
                    player_one=player_one,
                    player_two=player_two
                )
                matches_to_create.append(match)

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

    def _generate_remaining_schedule(self, players, existing_pairings):
        """
        Generate an optimal schedule for remaining unmatched player pairs.

        Uses a greedy algorithm to pack as many matches as possible into each round,
        ensuring no player plays more than once per round.

        Args:
            players: List of stage players
            existing_pairings: Set of existing pairing tuples (player_id1, player_id2)

        Returns:
            List of rounds, where each round is a list of (player1, player2) tuples
        """
        remaining_pairs = []
        for i, player1 in enumerate(players):
            for player2 in players[i+1:]:
                pairing_key = tuple(sorted([player1.id, player2.id]))
                if pairing_key not in existing_pairings:
                    remaining_pairs.append((player1, player2))

        if not remaining_pairs:
            return []

        schedule = []
        remaining_pairs = list(remaining_pairs)

        while remaining_pairs:
            round_matches = []
            used_players = set()

            for pair in remaining_pairs[:]:
                player1, player2 = pair
                if player1.id not in used_players and player2.id not in used_players:
                    round_matches.append(pair)
                    used_players.add(player1.id)
                    used_players.add(player2.id)
                    remaining_pairs.remove(pair)

            if round_matches:
                schedule.append(round_matches)

        return schedule

    def _get_existing_pairings(self, stage):
        """
        Get all existing pairings in the stage.

        Args:
            stage: The tournament stage

        Returns:
            set: Set of tuples representing existing pairings (player_id1, player_id2)
                 where player_id1 < player_id2
        """
        from tourney.models import Match

        pairings = set()
        matches = Match.objects.filter(round__stage=stage).select_related(
            'player_one', 'player_two')

        for match in matches:
            if match.player_one and match.player_two:
                pairing_key = tuple(
                    sorted([match.player_one.id, match.player_two.id]))
                pairings.add(pairing_key)

        return pairings

    def can_create_new_round(self, stage):
        """
        Determine if a new round can be created by checking if there are
        unmatched player pairs remaining.

        Args:
            stage: The tournament stage

        Returns:
            bool: True if at least two players haven't been matched together
        """
        from tourney.models import Player

        current_round = stage.get_current_round()
        if current_round is None:
            return False

        stage_players = list(stage.stage_players.filter(
            player__status=Player.PlayerStatus.ACTIVE))

        if len(stage_players) < 2:
            return False

        existing_pairings = self._get_existing_pairings(stage)

        for i, player1 in enumerate(stage_players):
            for player2 in stage_players[i+1:]:
                pairing_key = tuple(sorted([player1.id, player2.id]))
                if pairing_key not in existing_pairings:
                    return True

        return False

    def is_self_scheduled(self):
        return False

    def is_elimination_style(self):
        return False
