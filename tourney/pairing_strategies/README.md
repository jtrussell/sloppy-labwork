# Tournament Pairing Strategies

This directory contains all pairing strategies for the tournament system. Each strategy defines how players are paired for matches in tournament rounds.

## Architecture Overview

The pairing strategy system uses a plugin-style architecture with automatic discovery:

- **Base Class**: All strategies inherit from `PairingStrategy` in `base.py`
- **Auto-Discovery**: Strategies are automatically discovered and registered
- **Modular**: Each strategy lives in its own file for easy maintenance
- **Extensible**: Adding new strategies requires no changes to core code

## Creating a New Pairing Strategy

### Step 1: Create Your Strategy File

Create a new Python file in this directory (e.g., `my_strategy.py`):

```python
"""
My Custom Pairing Strategy

Brief description of what this strategy does.
"""

from .base import PairingStrategy

class MyCustomPairingStrategy(PairingStrategy):
    # Required metadata
    name = "my_custom"  # Machine-readable name (used in database)
    display_name = "My Custom Strategy"  # Human-readable name (shown in UI)
    description = "Brief description for forms and documentation"

    def make_pairings_for_round(self, round_obj):
        """
        Create match pairings for the given round.

        This is the main method you must implement. It should create
        Match objects and save them to the database.
        """
        # Your pairing logic here
        pass

    # Optional: Override behavior methods
    def is_seeding_required(self):
        """Return True if players need to be seeded before tournament starts."""
        return False

    def is_self_scheduled(self):
        """Return True if players create their own matches manually."""
        return False

    def is_elimination_style(self):
        """Return True if eliminated players should be hidden from standings."""
        return False

    def can_create_new_round(self, stage):
        """Return True if a new round can be created for this stage."""
        return super().can_create_new_round(stage)  # Use default logic
```

### Step 2: That's It!

Your strategy will be automatically discovered and made available in the tournament creation forms. No registration or configuration needed!

## Required Implementation

### Metadata (Required)

Every strategy must define these class attributes:

- `name`: Machine-readable identifier (used in database, URLs, etc.)
- `display_name`: Human-readable name shown in forms and UI
- `description`: Brief description of the strategy's behavior

### Core Method (Required)

- `make_pairings_for_round(round_obj)`: Create matches for the given round

### Optional Methods

- `can_create_new_round(stage)`: Control when new rounds can be created
- `is_seeding_required()`: Whether to show seeding confirmation UI
- `is_self_scheduled()`: Whether players create matches manually
- `is_elimination_style()`: Whether to hide eliminated players

## Implementation Guidelines

### Creating Matches

Use Django's bulk operations for efficiency:

```python
def make_pairings_for_round(self, round_obj):
    from tourney.models import Match, MatchResult

    # Get active players
    stage = round_obj.stage
    players = list(stage.stage_players.filter(
        player__status=Player.PlayerStatus.ACTIVE
    ))

    # Create your pairing logic
    matches = []
    for i in range(0, len(players), 2):
        if i + 1 < len(players):
            # Regular match
            match = Match(
                round=round_obj,
                player_one=players[i],
                player_two=players[i + 1]
            )
            matches.append(match)
        else:
            # Bye match (odd number of players)
            bye_match = Match(
                round=round_obj,
                player_one=players[i],
                player_two=None
            )
            matches.append(bye_match)

    # Save all matches at once
    Match.objects.bulk_create(matches)

    # Auto-resolve bye matches
    for match in matches:
        if match.is_bye():
            MatchResult.objects.create(
                match=match,
                winner=match.player_one
            )
```

### Accessing Tournament Data

Common data access patterns:

```python
# Get active players in this stage
active_players = stage.stage_players.filter(
    player__status=Player.PlayerStatus.ACTIVE
)

# Get results from previous rounds
from django.db.models import Q
previous_results = MatchResult.objects.filter(
    match__round__stage=stage,
    match__round__order__lt=round_obj.order
)

# Count wins for a player
wins = MatchResult.objects.filter(
    match__round__stage=stage,
    winner=player
).count()

# Get matches a player participated in
player_matches = Match.objects.filter(
    Q(player_one=player) | Q(player_two=player),
    round__stage=stage
)
```

### Error Handling

Strategies should handle edge cases gracefully:

```python
def make_pairings_for_round(self, round_obj):
    stage = round_obj.stage
    players = list(stage.stage_players.filter(
        player__status=Player.PlayerStatus.ACTIVE
    ))

    # Handle edge cases
    if len(players) == 0:
        return  # No players to pair

    if len(players) == 1:
        # Only one player - give them a bye
        bye_match = Match(
            round=round_obj,
            player_one=players[0],
            player_two=None
        )
        Match.objects.create(bye_match)
        MatchResult.objects.create(
            match=bye_match,
            winner=players[0]
        )
        return

    # Normal pairing logic...
```

## Testing Your Strategy

### Manual Testing

1. Create a tournament using your strategy
2. Register some test players
3. Create rounds and verify pairings work correctly
4. Test edge cases (odd players, no players, etc.)

### Automated Testing

Add tests to `tourney/tests.py`:

```python
def test_my_custom_strategy_pairing(self):
    from tourney.pairing_strategies.my_strategy import MyCustomPairingStrategy

    # Set up test tournament
    tournament = Tournament.objects.create(name="Test")
    stage = Stage.objects.create(
        tournament=tournament,
        name="Test Stage",
        pairing_strategy="my_custom"
    )

    # Add test players
    # Create round
    # Test pairing logic
    # Assert expected matches were created
```

## Available Strategies

### Swiss (`swiss.py`)
- **Use Case**: Balanced competition where all players play multiple rounds
- **Behavior**: Round 1 random, later rounds pair by standings
- **Best For**: Regular tournaments with 6+ players

### Single Elimination (`single_elimination.py`)
- **Use Case**: Quick tournaments with clear winner
- **Behavior**: Players eliminated after one loss
- **Best For**: Bracket-style competitions, large player counts

### Round Robin Self-Scheduled (`round_robin.py`)
- **Use Case**: Flexible scheduling where players arrange their own matches
- **Behavior**: No automatic pairing, players create matches manually
- **Best For**: Long-term leagues, casual play

## Common Patterns

### Seeded Pairing
For tournaments that need player seeding:
```python
def is_seeding_required(self):
    return True

def make_pairings_for_round(self, round_obj):
    if round_obj.order == 1:
        # First round - use seeds
        players = list(stage.stage_players.filter(
            player__status=Player.PlayerStatus.ACTIVE
        ).order_by('seed'))
```

### Swiss-Style Pairing
For standing-based pairing:
```python
def _get_players_by_standings(self, stage):
    # Sort by wins (desc), losses (asc), seed (asc)
    players_stats = []
    for player in stage.stage_players.filter(player__status=Player.PlayerStatus.ACTIVE):
        wins = MatchResult.objects.filter(
            match__round__stage=stage, winner=player
        ).count()
        # Calculate other stats...
        players_stats.append((player, wins, losses))

    players_stats.sort(key=lambda x: (-x[1], x[2], x[0].seed))
    return [player for player, wins, losses in players_stats]
```

### Custom Round Creation Rules
```python
def can_create_new_round(self, stage):
    # Custom logic for when rounds can be created
    current_round = stage.get_current_round()

    if not current_round:
        return True  # No rounds yet, can create first

    if not current_round.is_complete():
        return False  # Current round not finished

    # Custom condition: only create if >2 matches remain
    completed_matches = current_round.matches.filter(
        result__isnull=False
    ).count()

    return completed_matches > 2
```

## Debugging Tips

### Strategy Not Appearing in Forms
1. Check that your class inherits from `PairingStrategy`
2. Verify all required metadata (`name`, `display_name`, `description`) is set
3. Look for validation errors in console output
4. Ensure your file is in the `pairing_strategies/` directory

### Strategy Validation Errors
The system automatically validates strategies on startup. Check the console for:
```
Warning: Strategy MyStrategy has validation errors:
  - MyStrategy must define a 'name' class attribute
  - MyStrategy must implement make_pairings_for_round method
```

### Import Errors
If your strategy imports modules that don't exist:
```
Warning: Could not import strategy module tourney.pairing_strategies.my_strategy: No module named 'xyz'
```

### Testing Strategy Logic
Use Django shell for interactive testing:
```bash
python manage.py shell
```

```python
from tourney.pairing_strategies import get_pairing_strategy

strategy = get_pairing_strategy('my_custom')
# Test your strategy methods...
```

## Contributing

When contributing new strategies:

1. **Follow naming conventions**: Use descriptive, clear names
2. **Document thoroughly**: Add docstrings to all methods
3. **Handle edge cases**: Test with 0, 1, odd, and even player counts
4. **Add tests**: Include unit tests for your strategy
5. **Update this README**: Add your strategy to the "Available Strategies" section

## Need Help?

- Look at existing strategies for examples
- Check the base `PairingStrategy` class for available methods
- Review the tournament models in `tourney/models.py`
- Ask questions in project discussions or issues