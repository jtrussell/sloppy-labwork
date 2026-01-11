"""
Base Pairing Strategy Interface

All pairing strategies must inherit from the PairingStrategy class and implement
the required methods.
"""

from abc import ABC, abstractmethod


class PairingStrategy(ABC):
    """
    Abstract base class for all tournament pairing strategies.

    Each strategy defines how players are paired for matches in a tournament round.
    """

    # Strategy metadata - override in subclasses
    name = None  # Machine-readable name (e.g., 'swiss')
    display_name = None  # Human-readable name (e.g., 'Swiss')
    description = None  # Brief description of the strategy

    @abstractmethod
    def make_pairings_for_round(self, round_obj):
        """
        Create match pairings for the given round.

        Args:
            round_obj: The Round instance to create pairings for

        Returns:
            None (matches are created directly on the round)

        Raises:
            Any exception if pairings cannot be created
        """
        raise NotImplementedError("Subclasses must implement make_pairings_for_round")

    def can_create_new_round(self, stage):
        """
        Determine if a new round can be created for the stage.

        Args:
            stage: The Stage instance to check

        Returns:
            bool: True if a new round can be created, False otherwise
        """
        current_round = stage.get_current_round()
        return current_round is None or current_round.is_complete()

    def is_seeding_required(self):
        """
        Determine if player seeding is required before starting this strategy.

        Returns:
            bool: True if seeding confirmation UI should be shown
        """
        return False

    def is_self_scheduled(self):
        """
        Determine if this strategy allows players to create their own matches.

        Returns:
            bool: True if players can manually create matches
        """
        return False

    def is_elimination_style(self):
        """
        Determine if this is an elimination-style tournament.

        Returns:
            bool: True if eliminated players should be hidden from standings
        """
        return False

    def closes_registration_on_start(self):
        """
        Determine if starting this stage should automatically close registration.

        Returns:
            bool: True if registration should close when the first stage starts
        """
        return True

    @classmethod
    def validate_strategy(cls):
        """
        Validate that the strategy is properly implemented.

        Returns:
            list: List of validation error messages (empty if valid)
        """
        errors = []

        if not cls.name:
            errors.append(f"{cls.__name__} must define a 'name' class attribute")

        if not cls.display_name:
            errors.append(f"{cls.__name__} must define a 'display_name' class attribute")

        if not cls.description:
            errors.append(f"{cls.__name__} must define a 'description' class attribute")

        # Check that make_pairings_for_round is implemented
        if cls.make_pairings_for_round is PairingStrategy.make_pairings_for_round:
            errors.append(f"{cls.__name__} must implement make_pairings_for_round method")

        return errors

    def __str__(self):
        return self.display_name or self.__class__.__name__