"""
Swiss Pairing Strategy

A Swiss-system tournament strategy where players are paired based on their
current standings after the first round. Uses different algorithms based on
tournament size for optimal performance and pairing quality.
"""

import random
import itertools
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

        if len(stage_players) == 0:
            return

        if round_obj.order == 1:
            # First round: random pairing
            random.shuffle(stage_players)
            pairings = self._create_simple_pairings(stage_players)
        else:
            # Later rounds: use size-based algorithm
            if len(stage_players) <= 14:
                pairings = self._brute_force_pairing(round_obj, stage_players)
            else:
                pairings = self._greedy_backtrack_pairing(
                    round_obj, stage_players)

        # Create matches from pairings
        matches = []
        for player_one, player_two in pairings:
            match = Match(
                round=round_obj,
                player_one=player_one,
                player_two=player_two
            )
            matches.append(match)

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
                Q(match__player_one=stage_player) | Q(
                    match__player_two=stage_player),
                match__round__stage=stage
            ).exclude(winner=stage_player).exclude(winner=None).count()

            players_with_stats.append((stage_player, wins, losses))

        # Sort by wins (descending), then losses (ascending), then seed (ascending)
        players_with_stats.sort(key=lambda x: (-x[1], x[2], x[0].seed))
        return [player for player, wins, losses in players_with_stats]

    def _create_simple_pairings(self, stage_players):
        """
        Create simple consecutive pairings for first round.

        Args:
            stage_players: List of stage players (already shuffled)

        Returns:
            List of (player_one, player_two) tuples, with None for bye players
        """
        pairings = []
        for i in range(0, len(stage_players), 2):
            if i + 1 < len(stage_players):
                pairings.append((stage_players[i], stage_players[i + 1]))
            else:
                # Bye match
                pairings.append((stage_players[i], None))
        return pairings

    def _brute_force_pairing(self, round_obj, stage_players):
        """
        Brute force pairing algorithm for small tournaments (≤14 players).
        Tries to find good pairing solution with limited search.

        Args:
            round_obj: The round being paired
            stage_players: List of active stage players

        Returns:
            List of (player_one, player_two) tuples with optimal pairings
        """
        # Sort players by standings first
        sorted_players = self._get_sorted_players_by_standings(round_obj.stage)

        # Get previous opponents for each player
        previous_opponents = self._get_previous_opponents(round_obj.stage)

        # For small numbers, use the optimized search
        if len(sorted_players) <= 8:
            return self._exhaustive_search_pairing(sorted_players, previous_opponents, round_obj.order)
        else:
            # For 10-14 players, use a hybrid approach: try a few good options
            return self._smart_brute_force_pairing(sorted_players, previous_opponents, round_obj.order)

    def _greedy_backtrack_pairing(self, round_obj, stage_players):
        """
        Greedy + backtracking pairing algorithm for large tournaments (15+ players).
        Provides good practical solution without exponential complexity.

        Args:
            round_obj: The round being paired
            stage_players: List of active stage players

        Returns:
            List of (player_one, player_two) tuples with good pairings
        """
        # Sort players by standings
        sorted_players = self._get_sorted_players_by_standings(round_obj.stage)

        # Get previous opponents for each player
        previous_opponents = self._get_previous_opponents(round_obj.stage)

        # Handle odd number with improved bye selection
        if len(sorted_players) % 2 == 1:
            bye_history = self._get_bye_history(round_obj.stage)
            bye_player = self._select_bye_player(
                sorted_players, bye_history, previous_opponents, round_obj.order)

            remaining_players = [p for p in sorted_players if p.id != bye_player.id]

            # Try backtracking approach for remaining players
            result = []
            used = set()

            if self._backtrack_pair(remaining_players, result, used, 0, previous_opponents):
                return result + [(bye_player, None)]

            # Fallback to simple pairing if backtracking fails
            return self._force_pair_with_repeats(remaining_players, previous_opponents) + [(bye_player, None)]

        # Even number of players - original logic
        # Try backtracking approach
        result = []
        used = set()

        if self._backtrack_pair(sorted_players, result, used, 0, previous_opponents):
            return result

        # Fallback to simple pairing if backtracking fails
        return self._force_pair_with_repeats(sorted_players, previous_opponents)

    def _generate_perfect_matchings(self, players):
        """
        Generate all possible perfect matchings for a list of players.
        Uses itertools to create all combinations efficiently.
        """
        if len(players) == 0:
            return [[]]
        if len(players) == 2:
            return [[(players[0], players[1])]]

        matchings = []
        first_player = players[0]

        # Try pairing first player with each other player
        for i in range(1, len(players)):
            partner = players[i]
            remaining = players[1:i] + players[i+1:]

            # Get all matchings for remaining players
            for sub_matching in self._generate_perfect_matchings(remaining):
                matching = [(first_player, partner)] + sub_matching
                matchings.append(matching)

        return matchings

    def _calculate_matching_score(self, matching, previous_opponents):
        """
        Calculate the quality score for a complete matching.
        Higher scores are better.
        """
        MAX_POINT_DIFF = 1000  # Base score for identical records
        REPEAT_PENALTY = 10000  # Heavy penalty for repeat pairings

        total_score = 0
        for player_one, player_two in matching:
            if player_two is None:
                # Bye match - neutral score
                continue

            # Calculate score difference penalty
            score_diff = abs(self._get_player_score(
                player_one) - self._get_player_score(player_two))
            base_score = MAX_POINT_DIFF - score_diff

            # Check for repeat pairing
            has_played = player_two.id in previous_opponents.get(
                player_one.id, set())

            score = base_score
            if has_played:
                score -= REPEAT_PENALTY

            total_score += score

        return total_score

    def _backtrack_pair(self, players, current_pairing, used, start_index, previous_opponents):
        """
        Recursive backtracking function for greedy pairing algorithm.
        """
        MAX_ACCEPTABLE_DIFF = 2  # Maximum acceptable score difference

        if len(used) == len(players):
            return True

        # Handle odd number case - create bye for last unpaired player
        if len(used) == len(players) - 1:
            for player in players:
                if player.id not in used:
                    current_pairing.append((player, None))
                    return True

        # Find next unmatched player
        player_one = None
        for i in range(start_index, len(players)):
            if players[i].id not in used:
                player_one = players[i]
                break

        if player_one is None:
            return True

        # Try pairing with all valid opponents
        for player_two in players:
            if (player_two.id not in used and
                player_two.id != player_one.id and
                    self._is_good_pairing(player_one, player_two, previous_opponents, MAX_ACCEPTABLE_DIFF)):

                current_pairing.append((player_one, player_two))
                used.add(player_one.id)
                used.add(player_two.id)

                if self._backtrack_pair(players, current_pairing, used, 0, previous_opponents):
                    return True

                # Backtrack
                current_pairing.pop()
                used.remove(player_one.id)
                used.remove(player_two.id)

        return False

    def _is_good_pairing(self, player_one, player_two, previous_opponents, max_diff):
        """
        Check if a pairing is acceptable (no repeat and reasonable score difference).
        """
        score_diff = abs(self._get_player_score(player_one) -
                         self._get_player_score(player_two))
        has_played = player_two.id in previous_opponents.get(
            player_one.id, set())

        return not has_played and score_diff <= max_diff

    def _force_pair_with_repeats(self, players, previous_opponents):
        """
        Fallback pairing when backtracking fails - allows repeats if necessary.
        """
        pairings = []
        used = set()

        # Sort by score to minimize mismatches
        sorted_by_score = sorted(
            players, key=lambda p: -self._get_player_score(p))

        for i, player_one in enumerate(sorted_by_score):
            if player_one.id in used:
                continue

            # Find best available opponent
            best_opponent = None
            best_score = float('-inf')

            for player_two in sorted_by_score[i+1:]:
                if player_two.id in used:
                    continue

                # Score this pairing
                score_diff = abs(self._get_player_score(
                    player_one) - self._get_player_score(player_two))
                has_played = player_two.id in previous_opponents.get(
                    player_one.id, set())

                pairing_score = -score_diff
                if has_played:
                    pairing_score -= 100  # Penalty but not prohibitive

                if pairing_score > best_score:
                    best_score = pairing_score
                    best_opponent = player_two

            if best_opponent:
                pairings.append((player_one, best_opponent))
                used.add(player_one.id)
                used.add(best_opponent.id)
            else:
                # Bye match
                pairings.append((player_one, None))
                used.add(player_one.id)

        return pairings

    def _get_previous_opponents(self, stage):
        """
        Get a dictionary mapping player IDs to sets of opponent IDs they've played.
        """
        from tourney.models import Match

        opponents = {}

        # Get all completed matches in this stage
        matches = Match.objects.filter(
            round__stage=stage,
            result__isnull=False
        ).select_related('player_one', 'player_two', 'result')

        for match in matches:
            if match.player_one and match.player_two:
                # Add each as opponent of the other
                if match.player_one.id not in opponents:
                    opponents[match.player_one.id] = set()
                if match.player_two.id not in opponents:
                    opponents[match.player_two.id] = set()

                opponents[match.player_one.id].add(match.player_two.id)
                opponents[match.player_two.id].add(match.player_one.id)

        return opponents

    def _get_bye_history(self, stage):
        """
        Get a set of player IDs who have received byes in previous rounds.

        Returns:
            Set of stage_player IDs who have had byes
        """
        from tourney.models import Match

        bye_recipients = set()

        # Get all bye matches (where player_two is None)
        bye_matches = Match.objects.filter(
            round__stage=stage,
            player_two__isnull=True
        ).select_related('player_one')

        for match in bye_matches:
            if match.player_one:
                bye_recipients.add(match.player_one.id)

        return bye_recipients

    def _select_bye_player(self, sorted_players, bye_history, previous_opponents, round_number):
        """
        Select the best player to receive a bye based on the Swiss bye rules:
        - Round 1: Random selection
        - Later rounds: Lowest ranked player who hasn't had a bye yet
        - Exception: Allow repeat bye to avoid repeat pairings

        Args:
            sorted_players: List of stage players sorted by standings (best to worst)
            bye_history: Set of player IDs who have had byes
            previous_opponents: Dict of player ID to set of opponent IDs
            round_number: Current round number

        Returns:
            StagePlayer who should receive the bye
        """
        if round_number == 1:
            # Round 1: Random bye assignment
            return random.choice(sorted_players)

        # Find players who haven't had a bye yet, starting from lowest ranked
        players_without_byes = []
        for player in reversed(sorted_players):  # Start from lowest ranked
            if player.id not in bye_history:
                players_without_byes.append(player)

        if players_without_byes:
            # Check if giving bye to lowest ranked player without bye would force repeat pairings
            candidate_bye_player = players_without_byes[0]  # Lowest ranked without bye

            # Test if we can make valid pairings with this bye selection
            remaining_players = [p for p in sorted_players if p.id != candidate_bye_player.id]
            if self._can_pair_without_repeats(remaining_players, previous_opponents):
                return candidate_bye_player

            # If lowest ranked causes pairing issues, try next lowest without bye
            for candidate in players_without_byes[1:]:
                remaining_players = [p for p in sorted_players if p.id != candidate.id]
                if self._can_pair_without_repeats(remaining_players, previous_opponents):
                    return candidate

        # Fallback: If no valid non-repeat bye exists, give bye to lowest ranked overall
        # This handles the case where avoiding repeat byes would force repeat pairings
        return sorted_players[-1]  # Lowest ranked player

    def _can_pair_without_repeats(self, players, previous_opponents):
        """
        Check if a list of players can be paired without any repeat pairings.

        Args:
            players: List of stage players to pair
            previous_opponents: Dict of player ID to set of opponent IDs

        Returns:
            Boolean indicating if valid pairing exists
        """
        if len(players) % 2 != 0:
            return False  # Can't pair odd number of players

        # Use backtracking to properly check if valid pairing exists
        return self._backtrack_check_pairing(players, set(), previous_opponents)

    def _backtrack_check_pairing(self, players, used, previous_opponents):
        """
        Recursively check if players can be paired without repeats using backtracking.

        Args:
            players: List of all players to pair
            used: Set of player IDs already paired
            previous_opponents: Dict of player ID to set of opponent IDs

        Returns:
            Boolean indicating if valid pairing exists
        """
        # Base case: all players are paired
        if len(used) == len(players):
            return True

        # Find first unpaired player
        player_one = None
        for player in players:
            if player.id not in used:
                player_one = player
                break

        if player_one is None:
            return True

        # Try pairing with each other unpaired player
        for player_two in players:
            if (player_two.id not in used and
                player_two.id != player_one.id and
                player_two.id not in previous_opponents.get(player_one.id, set())):

                # Try this pairing
                used.add(player_one.id)
                used.add(player_two.id)

                if self._backtrack_check_pairing(players, used, previous_opponents):
                    return True

                # Backtrack
                used.remove(player_one.id)
                used.remove(player_two.id)

        return False

    def _get_player_score(self, stage_player):
        """
        Get a player's current score (wins) for sorting purposes.
        """
        from tourney.models import MatchResult

        return MatchResult.objects.filter(
            match__round__stage=stage_player.stage,
            winner=stage_player
        ).count()

    def _exhaustive_search_pairing(self, sorted_players, previous_opponents, round_number=None):
        """
        Exhaustive search for small tournaments (≤8 players).
        Uses improved bye selection logic.
        """
        # Handle odd number of players
        if len(sorted_players) % 2 == 1:
            # Use improved bye selection if we have round information
            if round_number is not None:
                stage = sorted_players[0].stage if sorted_players else None
                if stage:
                    bye_history = self._get_bye_history(stage)
                    bye_player = self._select_bye_player(
                        sorted_players, bye_history, previous_opponents, round_number)

                    remaining_players = [p for p in sorted_players if p.id != bye_player.id]

                    # Find best pairing for remaining players
                    matchings = self._generate_perfect_matchings(remaining_players)
                    if matchings:
                        best_score = float('-inf')
                        best_pairing = None

                        for matching in matchings:
                            score = self._calculate_matching_score(matching, previous_opponents)
                            if score > best_score:
                                best_score = score
                                best_pairing = matching

                        if best_pairing:
                            return best_pairing + [(bye_player, None)]

            # Fallback to old logic if no round info or stage
            best_bye_pairings = None
            best_bye_score = float('-inf')

            for bye_idx in range(len(sorted_players)):
                # Try this player as bye
                remaining_players = sorted_players[:bye_idx] + \
                    sorted_players[bye_idx+1:]
                bye_player = sorted_players[bye_idx]

                # Find best pairing for remaining players
                matchings = self._generate_perfect_matchings(remaining_players)
                for matching in matchings:
                    score = self._calculate_matching_score(
                        matching, previous_opponents)
                    if score > best_bye_score:
                        best_bye_score = score
                        best_bye_pairings = matching + [(bye_player, None)]

            return best_bye_pairings or [(sorted_players[0], None)]

        # Even number of players - find best perfect matching
        best_pairings = None
        best_score = float('-inf')

        matchings = self._generate_perfect_matchings(sorted_players)
        for matching in matchings:
            score = self._calculate_matching_score(
                matching, previous_opponents)
            if score > best_score:
                best_score = score
                best_pairings = matching

        return best_pairings or self._create_simple_pairings(sorted_players)

    def _smart_brute_force_pairing(self, sorted_players, previous_opponents, round_number=None):
        """
        Smart brute force for medium tournaments (9-14 players).
        Uses greedy approach with backtracking, limited search.
        """
        # Handle odd number with improved bye selection
        if len(sorted_players) % 2 == 1 and round_number is not None:
            stage = sorted_players[0].stage if sorted_players else None
            if stage:
                bye_history = self._get_bye_history(stage)
                bye_player = self._select_bye_player(
                    sorted_players, bye_history, previous_opponents, round_number)

                remaining_players = [p for p in sorted_players if p.id != bye_player.id]

                # Try the greedy backtracking approach for remaining players
                result = []
                used = set()

                if self._backtrack_pair(remaining_players, result, used, 0, previous_opponents):
                    return result + [(bye_player, None)]

                # Fallback to force pairing
                pairings = self._force_pair_with_repeats(remaining_players, previous_opponents)
                return pairings + [(bye_player, None)]

        # Original logic for even numbers or when no round info
        # Try the greedy backtracking approach first
        result = []
        used = set()

        if self._backtrack_pair(sorted_players, result, used, 0, previous_opponents):
            return result

        # If that fails, try a few greedy approaches
        best_pairings = None
        best_score = float('-inf')

        # Try different starting points (rotate the player order)
        for start_offset in range(min(4, len(sorted_players))):
            rotated_players = sorted_players[start_offset:] + \
                sorted_players[:start_offset]
            pairings = self._force_pair_with_repeats(
                rotated_players, previous_opponents)
            score = self._calculate_matching_score(
                pairings, previous_opponents)

            if score > best_score:
                best_score = score
                best_pairings = pairings

        return best_pairings or self._create_simple_pairings(sorted_players)
