"""
Swiss Pairing Strategy

A Swiss-system tournament strategy where players are paired based on their
current standings after the first round.
"""

import random
from django.db.models import Q

from .base import PairingStrategy


class SwissPairingStrategy(PairingStrategy):
    """
    Swiss pairing strategy implementation.

    In Swiss pairing:
    - Round 1: Players are paired randomly
    - Later rounds: Players are sorted by wins/losses and paired consecutively
    - Players with similar records play each other
    - Bye matches are created for odd numbers of players
    """

    name = "swiss"
    display_name = "Swiss"
    description = "Players paired by standings after random first round"

    def is_elimination_style(self):
        return False

    def make_pairings_for_round(self, round_obj):
        from tourney.models import Player, Match, MatchResult

        stage = round_obj.stage
        stage_players = list(stage.stage_players.filter(
            player__status=Player.PlayerStatus.ACTIVE))

        if round_obj.order == 1:
            # First round: random pairing
            random.shuffle(stage_players)
        else:
            # Later rounds: pair by standings
            stage_players = self._get_sorted_players_by_standings(stage)

        matches = []
        paired_players = set()

        # Create pairings
        for i in range(0, len(stage_players), 2):
            if i + 1 < len(stage_players):
                # Regular match between two players
                player_one = stage_players[i]
                player_two = stage_players[i + 1]

                if player_one.id not in paired_players and player_two.id not in paired_players:
                    match = Match(
                        round=round_obj,
                        player_one=player_one,
                        player_two=player_two
                    )
                    matches.append(match)
                    paired_players.add(player_one.id)
                    paired_players.add(player_two.id)
            else:
                # Odd number of players - create bye match
                if stage_players[i].id not in paired_players:
                    bye_match = Match(
                        round=round_obj,
                        player_one=stage_players[i],
                        player_two=None
                    )
                    matches.append(bye_match)
                    paired_players.add(stage_players[i].id)

        # Save all matches
        Match.objects.bulk_create(matches)

        # Auto-resolve bye matches
        for match in matches:
            if match.is_bye():
                MatchResult.objects.create(
                    match=match,
                    winner=match.player_one
                )

    def _get_sorted_players_by_standings(self, stage):
        """
        Sort players by their current standings (wins, then losses, then seed).

        Args:
            stage: The stage to get standings for

        Returns:
            List of stage_players sorted by performance
        """
        from tourney.models import Player, MatchResult

        players_with_stats = []
        for stage_player in stage.stage_players.filter(player__status=Player.PlayerStatus.ACTIVE):
            # Count wins
            wins = MatchResult.objects.filter(
                match__round__stage=stage,
                winner=stage_player
            ).count()

            # Count losses (matches where player participated but didn't win)
            losses = MatchResult.objects.filter(
                Q(match__player_one=stage_player) | Q(match__player_two=stage_player),
                match__round__stage=stage
            ).exclude(winner=stage_player).exclude(winner=None).count()

            players_with_stats.append((stage_player, wins, losses))

        # Sort by wins (descending), then losses (ascending), then seed (ascending)
        players_with_stats.sort(key=lambda x: (-x[1], x[2], x[0].seed))
        return [player for player, wins, losses in players_with_stats]