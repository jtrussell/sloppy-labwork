"""
Pairing Strategies Package

This package contains all tournament pairing strategies. Each strategy should
be implemented as a separate module following the base PairingStrategy interface.
"""

from .base import PairingStrategy
from .registry import get_pairing_strategy, get_available_strategies, get_strategy_choices

__all__ = ['PairingStrategy', 'get_pairing_strategy', 'get_available_strategies', 'get_strategy_choices']