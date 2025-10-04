"""
Pairing Strategy Registry

Automatic discovery and registration system for pairing strategies.
"""

import importlib
import inspect
import os
from pathlib import Path
from typing import Dict, List, Type

from .base import PairingStrategy


class StrategyRegistry:
    """Registry for pairing strategies with automatic discovery."""

    def __init__(self):
        self._strategies: Dict[str, Type[PairingStrategy]] = {}
        self._discovered = False

    def discover_strategies(self):
        """Automatically discover and register all strategy classes."""
        if self._discovered:
            return

        # Get the directory containing strategy modules
        strategies_dir = Path(__file__).parent

        # Import all Python files in the strategies directory
        for file_path in strategies_dir.glob("*.py"):
            if file_path.stem in ['__init__', 'base', 'registry']:
                continue

            module_name = f"tourney.pairing_strategies.{file_path.stem}"
            try:
                module = importlib.import_module(module_name)

                # Find all PairingStrategy subclasses in the module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, PairingStrategy) and
                        obj is not PairingStrategy and
                            hasattr(obj, 'name') and obj.name):

                        # Validate the strategy
                        errors = obj.validate_strategy()
                        if errors:
                            print(
                                f"Warning: Strategy {obj.__name__} has validation errors:")
                            for error in errors:
                                print(f"  - {error}")
                            continue

                        # Register the strategy
                        self._strategies[obj.name] = obj

            except ImportError as e:
                print(
                    f"Warning: Could not import strategy module {module_name}: {e}")

        self._discovered = True

    def register_strategy(self, strategy_class: Type[PairingStrategy]):
        """
        Manually register a strategy class.

        Args:
            strategy_class: The strategy class to register
        """
        if not issubclass(strategy_class, PairingStrategy):
            raise ValueError("Strategy must inherit from PairingStrategy")

        errors = strategy_class.validate_strategy()
        if errors:
            raise ValueError(
                f"Strategy validation failed: {', '.join(errors)}")

        self._strategies[strategy_class.name] = strategy_class

    def get_strategy(self, name: str) -> Type[PairingStrategy]:
        """
        Get a strategy class by name.

        Args:
            name: The strategy name

        Returns:
            The strategy class

        Raises:
            ValueError: If strategy is not found
        """
        self.discover_strategies()
        strategy_class = self._strategies.get(name)
        if not strategy_class:
            available = list(self._strategies.keys())
            raise ValueError(
                f"Unknown pairing strategy: {name}. Available: {available}")
        return strategy_class

    def get_available_strategies(self) -> Dict[str, Type[PairingStrategy]]:
        """
        Get all available strategies.

        Returns:
            Dictionary mapping strategy names to strategy classes
        """
        self.discover_strategies()
        return self._strategies.copy()

    def get_strategy_choices(self) -> List[tuple]:
        """
        Get strategy choices formatted for Django forms.

        Returns:
            List of (name, display_name) tuples
        """
        self.discover_strategies()
        choices = [(name, cls.display_name)
                   for name, cls in self._strategies.items()]
        return choices


# Global registry instance
_registry = StrategyRegistry()


def get_pairing_strategy(strategy_name: str) -> PairingStrategy:
    """
    Get a pairing strategy instance by name.

    Args:
        strategy_name: The name of the strategy to get

    Returns:
        An instance of the requested pairing strategy

    Raises:
        ValueError: If the strategy is not found
    """
    strategy_class = _registry.get_strategy(strategy_name)
    return strategy_class()


def get_available_strategies() -> Dict[str, Type[PairingStrategy]]:
    """
    Get all available pairing strategies.

    Returns:
        Dictionary mapping strategy names to strategy classes
    """
    return _registry.get_available_strategies()


def get_strategy_choices() -> List[tuple]:
    """
    Get strategy choices formatted for Django forms.

    Returns:
        List of (name, display_name) tuples
    """
    return _registry.get_strategy_choices()


def register_strategy(strategy_class: Type[PairingStrategy]):
    """
    Manually register a pairing strategy.

    Args:
        strategy_class: The strategy class to register
    """
    _registry.register_strategy(strategy_class)
