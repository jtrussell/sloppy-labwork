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
        from tourney.models import Player, Match, MatchResult

        stage = round_obj.stage

        if round_obj.order == 1:
            # First round: pair players by seed
            stage_players = list(stage.stage_players.filter(
                player__status=Player.PlayerStatus.ACTIVE).order_by('seed'))
        else:
            # Later rounds: only winners from previous round
            stage_players = self._get_winners_from_previous_round(stage, round_obj)

        matches = []
        for i in range(0, len(stage_players), 2):
            if i + 1 < len(stage_players):
                # Regular match between two players
                match = Match(
                    round=round_obj,
                    player_one=stage_players[i],
                    player_two=stage_players[i + 1]
                )
                matches.append(match)
            else:
                # Odd number of players - create bye match
                bye_match = Match(
                    round=round_obj,
                    player_one=stage_players[i],
                    player_two=None
                )
                matches.append(bye_match)

        # Save all matches
        Match.objects.bulk_create(matches)

        # Auto-resolve bye matches
        for match in matches:
            if match.is_bye():
                MatchResult.objects.create(
                    match=match,
                    winner=match.player_one
                )

    def _get_winners_from_previous_round(self, stage, current_round):
        """
        Get the winners from the previous round to advance to the current round.

        Args:
            stage: The tournament stage
            current_round: The current round

        Returns:
            List of stage_players who won in the previous round
        """
        previous_round = stage.rounds.filter(order=current_round.order - 1).first()
        if not previous_round:
            return []

        winners = []
        for match in previous_round.matches.all():
            if match.has_result() and match.result.winner:
                winners.append(match.result.winner)

        return winners

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
            # Check if we have more than one completed match
            # (if only 1 or 0 matches completed, tournament should end)
            completed_matches = current_round.matches.filter(
                result__isnull=False).count()
            if completed_matches <= 1:
                return False

        return True