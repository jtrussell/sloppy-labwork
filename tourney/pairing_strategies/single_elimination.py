"""
Single Elimination Pairing Strategy

A single-elimination tournament strategy where players are eliminated after
losing a single match.
"""

from .base import PairingStrategy


class SingleEliminationPairingStrategy(PairingStrategy):
    """
    Single elimination pairing strategy implementation.

    In single elimination:
    - Round 1: Players are seeded and paired (1 vs N, 2 vs N-1, etc.)
    - Later rounds: Only winners advance to the next round
    - Eliminated players are not shown in standings
    - Tournament continues until only one player remains
    """

    name = "single_elimination"
    display_name = "Single Elimination"
    description = "Players eliminated after one loss, winners advance"

    def is_seeding_required(self):
        return True

    def is_elimination_style(self):
        return True

    def make_pairings_for_round(self, round_obj):
        if round_obj.order == 1:
            super().make_pairings_for_round(round_obj)
            return

        stage = round_obj.stage
        previous_round = stage.rounds.filter(order=round_obj.order - 1).first()
        winners = self._get_round_winners(previous_round)
        for pod_winners in self._group_by_pod(winners, stage):
            self.make_pairings_for_players(round_obj, pod_winners)

    def make_pairings_for_players(self, round_obj, stage_players):
        from tourney.models import Match, MatchResult
        import math

        if round_obj.order == 1:
            stage_players = sorted(stage_players, key=lambda sp: sp.seed)
        else:
            stage_players = list(stage_players)

        if not stage_players:
            return

        matches = []
        num_players = len(stage_players)

        # Calculate how many byes are needed to reach next power of 2
        next_power_of_2 = 2 ** math.ceil(math.log2(num_players)) if num_players > 1 else 1
        num_byes = next_power_of_2 - num_players

        # Top seeds get byes
        for i in range(num_byes):
            bye_match = Match(
                round=round_obj,
                player_one=stage_players[i],
                player_two=None
            )
            matches.append(bye_match)

        # Remaining players pair up using bracket-style seeding
        # After byes, we have stage_players[num_byes:] to pair
        remaining_players = stage_players[num_byes:]
        num_remaining = len(remaining_players)

        # Pair first with last, second with second-to-last, etc.
        i = 0
        j = num_remaining - 1

        while i < j:
            match = Match(
                round=round_obj,
                player_one=remaining_players[i],
                player_two=remaining_players[j]
            )
            matches.append(match)
            i += 1
            j -= 1

        # Save all matches
        Match.objects.bulk_create(matches)

        # Auto-resolve bye matches
        for match in matches:
            if match.is_bye():
                MatchResult.objects.create(
                    match=match,
                    winner=match.player_one
                )

    def _get_round_winners(self, round_obj):
        if not round_obj:
            return []

        winners = []
        for match in round_obj.matches.all():
            if match.has_result() and match.result.winner:
                winners.append(match.result.winner)

        return winners

    def _group_by_pod(self, stage_players, stage):
        if not stage.has_pods():
            return [stage_players]

        groups = {}
        for stage_player in stage_players:
            groups.setdefault(stage_player.pod_id, []).append(stage_player)
        return list(groups.values())

    def can_create_new_round(self, stage):
        """
        Override base implementation to prevent creating rounds when there's
        only one winner remaining.

        Args:
            stage: The tournament stage

        Returns:
            bool: True if a new round can be created
        """
        if not super().can_create_new_round(stage):
            return False

        current_round = stage.get_current_round()
        if current_round:
            winners = self._get_round_winners(current_round)
            return any(
                len(pod_winners) > 1
                for pod_winners in self._group_by_pod(winners, stage))

        return True
