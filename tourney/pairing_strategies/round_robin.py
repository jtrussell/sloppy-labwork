"""
Round Robin Self-Scheduled Pairing Strategy

A round robin tournament strategy where players schedule their own matches
against all other players.
"""

from .base import PairingStrategy


class RoundRobinSelfScheduledPairingStrategy(PairingStrategy):
    """
    Round robin self-scheduled pairing strategy implementation.

    In round robin self-scheduled:
    - No automatic pairing is performed
    - Players manually create matches against opponents
    - All players play against all other players eventually
    - No elimination - all players remain active throughout
    """

    name = "round_robin"
    display_name = "Free-For-All"
    description = "Players create matches against each other manually"

    def make_pairings_for_round(self, round_obj):
        """
        No automatic pairings are created in self-scheduled tournaments.
        Players create matches manually through the UI.
        """
        pass

    def can_create_new_round(self, stage):
        """
        Prevent automatic round creation in self-scheduled tournaments.

        Args:
            stage: The tournament stage

        Returns:
            bool: Always False for self-scheduled tournaments
        """
        return False

    def is_self_scheduled(self):
        return True

    def is_elimination_style(self):
        return False

    def closes_registration_on_start(self):
        return False