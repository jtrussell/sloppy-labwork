from enum import unique
from django.contrib.auth.models import User
from django.db import models
from django.db.models import UniqueConstraint
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from django.utils.crypto import get_random_string
import random
from abc import ABC, abstractmethod
from .pairing_strategies import get_pairing_strategy


def generate_tournament_code():
    """Generate a unique 6-character code for tournament URLs."""
    length = 6
    while True:
        code = get_random_string(
            length, allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        if not Tournament.objects.filter(code=code).exists():
            return code


class Tournament(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(default=None, null=True, blank=True)
    code = models.CharField(
        max_length=6,
        unique=True,
        help_text="Unique code used in URLs for security"
    )
    owner = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name='owned_tournaments', null=True, blank=True)
    is_accepting_registrations = models.BooleanField(default=True)
    is_closed = models.BooleanField(default=False)
    is_public = models.BooleanField(
        default=False,
        help_text="Allow unauthenticated users to view standings and matches"
    )
    pmc_event = models.ForeignKey(
        'pmc.Event', on_delete=models.SET_NULL,
        related_name='tournaments', default=None, null=True, blank=True,
        help_text="KeyChain event this tournament was exported to"
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_on']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Generate code if it doesn't exist
        if not self.code:
            self.code = generate_tournament_code()
        super().save(*args, **kwargs)

    def is_user_admin(self, user):
        if user == self.owner:
            return True
        return self.tournament_admins.filter(user=user).exists()

    def get_current_stage(self):
        """
        Returns the current stage - defined as the latest stage that has rounds,
        or the first stage if no rounds exist yet.
        """
        stages_with_rounds = self.stages.filter(
            rounds__isnull=False).distinct().order_by('-order')
        if stages_with_rounds.exists():
            return stages_with_rounds.first()
        return self.stages.order_by('order').first()

    def get_active_players(self):
        return self.players.filter(status=Player.PlayerStatus.ACTIVE)

    def create_initial_stage(self, main_pairing_strategy='swiss', main_max_players=None,
                             main_allow_ties=False, main_score_reporting=0, main_round_length=None):
        if not self.stages.exists():
            stage = Stage.objects.create(
                tournament=self,
                name='Main Stage',
                order=1,
                pairing_strategy=main_pairing_strategy,
                max_players=main_max_players,
                are_ties_allowed=main_allow_ties,
                report_full_scores=main_score_reporting,
                round_length_in_minutes=main_round_length
            )

            stage.set_ranking_criteria(get_default_main_stage_criteria())

            for i, player in enumerate(self.get_active_players()):
                StagePlayer.objects.create(
                    player=player,
                    stage=stage,
                    seed=i + 1
                )

            return stage
        return self.get_current_stage()

    def create_playoff_stage(self, max_players=8, playoff_score_reporting=0, playoff_round_length=None):
        if self.stages.filter(order=2).exists():
            return self.stages.get(order=2)

        stage = Stage.objects.create(
            tournament=self,
            name='Playoff Stage',
            order=2,
            pairing_strategy='single_elimination',
            max_players=max_players,
            are_ties_allowed=False,  # Playoffs never allow ties
            report_full_scores=playoff_score_reporting,
            round_length_in_minutes=playoff_round_length
        )

        stage.set_ranking_criteria(get_default_playoff_stage_criteria())
        return stage

    def get_next_stage(self):
        """
        Returns the next stage after the current stage, if it exists.
        """
        current_stage = self.get_current_stage()
        if current_stage:
            return self.stages.filter(order__gt=current_stage.order).order_by('order').first()
        return None

    def can_create_round_in_current_stage(self):
        """
        Returns True if a new round can be created in the current stage.
        """
        current_stage = self.get_current_stage()
        if not current_stage:
            return False

        pairing_strategy = get_pairing_strategy(current_stage.pairing_strategy)
        return pairing_strategy.can_create_new_round(current_stage)

    def can_start_next_stage(self):
        """
        Returns True if the next stage can be started (current stage is complete 
        and next stage exists but has no rounds yet).
        """
        current_stage = self.get_current_stage()
        next_stage = self.get_next_stage()

        if not current_stage or not next_stage:
            return False

        # Current stage must be complete
        if not current_stage.is_complete():
            return False

        # Next stage must not have any rounds yet
        return not next_stage.rounds.exists()

    def prepare_next_stage_seeding(self):
        """
        Prepares the next stage by creating preliminary StagePlayer records
        based on current standings. No rounds are created yet.
        """
        current_stage = self.get_current_stage()
        next_stage = self.get_next_stage()

        if not self.can_start_next_stage():
            raise ValueError("Cannot prepare next stage at this time")

        # Clear any existing preliminary seeding (in case admin re-prepares)
        if not next_stage.rounds.exists():
            next_stage.stage_players.all().delete()

        # Get current standings from the current stage
        standings = StandingCalculator.get_stage_standings(current_stage)

        # Set ranks on current stage players before advancement
        for i, standing in enumerate(standings):
            standing['stage_player'].rank = i + 1
            standing['stage_player'].save()

        # For seeding confirmation, show ALL active players initially
        # Filtering to max_players will happen when the stage actually starts
        active_standings = [
            s for s in standings if s['stage_player'].player.status == Player.PlayerStatus.ACTIVE]

        # Create preliminary stage players for ALL active players (for seeding confirmation)
        for i, standing in enumerate(active_standings):
            StagePlayer.objects.create(
                player=standing['stage_player'].player,
                stage=next_stage,
                seed=i + 1  # Seed 1 for 1st place, seed 2 for 2nd place, etc.
            )

        return next_stage

    def can_modify_next_stage_seeding(self):
        """
        Returns True if the next stage seeding can be modified (no rounds exist yet).
        """
        next_stage = self.get_next_stage()
        if not next_stage:
            return False
        return not next_stage.rounds.exists()

    def advance_to_next_stage(self):
        """
        Finalizes advancement to the next stage by creating the first round.
        Assumes StagePlayer records already exist (from prepare_next_stage_seeding).
        """
        next_stage = self.get_next_stage()

        if not next_stage:
            raise ValueError("No next stage found")

        if next_stage.rounds.exists():
            raise ValueError("Next stage already has rounds")

        if not next_stage.stage_players.exists():
            raise ValueError("No players seeded for next stage")

        # Apply max_players limit now (remove excess players if needed)
        if next_stage.max_players:
            stage_players = next_stage.stage_players.order_by('seed')
            players_to_remove = stage_players[next_stage.max_players:]
            for stage_player in players_to_remove:
                stage_player.delete()

        # Create first round in next stage
        pairing_strategy = get_pairing_strategy(next_stage.pairing_strategy)

        next_order = (next_stage.rounds.aggregate(
            models.Max('order'))['order__max'] or 0) + 1
        new_round = Round.objects.create(
            stage=next_stage,
            order=next_order,
            round_length_in_minutes=next_stage.round_length_in_minutes
        )

        pairing_strategy.make_pairings_for_round(new_round)

        return next_stage

    def get_active_timer(self):
        """Returns the active CountdownTimer for this tournament, or None."""
        tt = self.tournament_timers.filter(is_active=True).first()
        return tt.timer if tt else None

    def create_round_timer(self, round_obj, owner):
        """Create a paused timer for a round. Deletes old timers first."""
        from timekeeper.models import CountdownTimer

        if not round_obj.round_length_in_minutes:
            return None

        for tt in self.tournament_timers.all():
            tt.timer.delete()

        seconds = round_obj.round_length_in_minutes * 60
        timer = CountdownTimer.objects.create(
            name=f'{self.name} - Round {round_obj.order}',
            owner=owner,
            pause_time_remaining_seconds=seconds,
            original_duration_seconds=seconds
        )

        TournamentTimer.objects.create(
            tournament=self,
            timer=timer,
            is_active=True
        )

        return timer


class Player(models.Model):
    class PlayerStatus(models.TextChoices):
        ACTIVE = 'active', _('Active')
        DROPPED = 'dropped', _('Dropped')

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name='tournament_players',
        null=True, blank=True, help_text="Leave empty for guest players")
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name='players')
    status = models.CharField(
        max_length=10, choices=PlayerStatus.choices, default=PlayerStatus.ACTIVE)
    nickname = models.CharField(
        max_length=100, default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    # has_seen_completion_message = models.BooleanField(default=False)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=['user', 'tournament'],
                condition=models.Q(user__isnull=False),
                name='unique_tournament_player'
            ),
            UniqueConstraint(
                fields=['nickname', 'tournament'],
                condition=models.Q(user__isnull=True),
                name='unique_guest_player'
            ),
        ]
        ordering = ['created_on']

    def __str__(self):
        name = self.get_display_name()
        guest_indicator = " (Guest)" if self.is_guest() else ""
        try:
            tournament_name = self.tournament.name if self.tournament_id else "No Tournament"
        except:
            tournament_name = "No Tournament"
        return f'{name}{guest_indicator} - {tournament_name}'

    def get_display_name(self):
        if self.user:
            return self.nickname or self.user.username
        return self.nickname or "Guest Player"

    def is_guest(self):
        return self.user is None

    def get_username_display(self):
        return self.user.username if self.user else "(Guest)"


class TournamentAdmin(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name='tournament_admin_roles', null=True, blank=True)
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name='tournament_admins')
    name = models.CharField(
        max_length=100, default=None, null=True, blank=True)
    description = models.TextField(default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['user', 'tournament'],
                             name='unique_tournament_admin'),
        ]

    def __str__(self):
        return f'{self.user.username} - {self.tournament.name}'


class RankingCriterion(ABC):
    @abstractmethod
    def get_key(self):
        pass

    @abstractmethod
    def get_name(self):
        pass

    @abstractmethod
    def get_description(self):
        pass

    @abstractmethod
    def calculate_value(self, stage_player, stage, standings_cache=None):
        pass

    @abstractmethod
    def is_descending(self):
        pass


class WinsRankingCriterion(RankingCriterion):
    def get_key(self):
        return 'wins'

    def get_name(self):
        return 'Wins'

    def get_description(self):
        return 'Number of match wins'

    def calculate_value(self, stage_player, stage, standings_cache=None):
        if standings_cache and stage_player.id in standings_cache:
            return standings_cache[stage_player.id].get('wins', 0)

        return MatchResult.objects.filter(
            match__round__stage=stage,
            winner=stage_player
        ).count()

    def is_descending(self):
        return True


class LossesRankingCriterion(RankingCriterion):
    def get_key(self):
        return 'losses'

    def get_name(self):
        return 'Losses'

    def get_description(self):
        return 'Number of match losses (fewer is better)'

    def calculate_value(self, stage_player, stage, standings_cache=None):
        if standings_cache and stage_player.id in standings_cache:
            return standings_cache[stage_player.id].get('losses', 0)

        return MatchResult.objects.filter(
            Q(match__player_one=stage_player) | Q(
                match__player_two=stage_player),
            match__round__stage=stage
        ).exclude(winner=stage_player).exclude(winner=None).count()

    def is_descending(self):
        return False


class PointsRankingCriterion(RankingCriterion):
    def get_key(self):
        return 'points'

    def get_name(self):
        return 'Points'

    def get_description(self):
        return 'Number of points (2 for win, 1 for tie)'

    def calculate_value(self, stage_player, stage, standings_cache=None):
        if standings_cache and stage_player.id in standings_cache:
            return standings_cache[stage_player.id].get('points', 0)

        wins = MatchResult.objects.filter(
            match__round__stage=stage,
            winner=stage_player
        ).count()

        ties = MatchResult.objects.filter(
            Q(match__player_one=stage_player) | Q(
                match__player_two=stage_player),
            match__round__stage=stage,
            winner=None
        ).count()

        return wins * 2 + ties * 1

    def is_descending(self):
        return True


class StrengthOfScheduleRankingCriterion(RankingCriterion):
    def get_key(self):
        return 'strength_of_schedule'

    def get_name(self):
        return 'SoS'

    def get_description(self):
        return 'Average points of opponents faced'

    def calculate_value(self, stage_player, stage, standings_cache=None):
        if standings_cache and stage_player.id in standings_cache:
            return standings_cache[stage_player.id].get('strength_of_schedule', 0)

        opponents = self._get_opponents(stage_player, stage)
        if not opponents:
            return 0

        total_opponent_points = 0
        for opponent in opponents:
            opponent_wins = MatchResult.objects.filter(
                match__round__stage=stage,
                winner=opponent
            ).count()

            opponent_ties = MatchResult.objects.filter(
                Q(match__player_one=opponent) | Q(match__player_two=opponent),
                match__round__stage=stage,
                winner=None
            ).count()

            total_opponent_points += (opponent_wins * 2 + opponent_ties * 1)

        return total_opponent_points / len(opponents) if opponents else 0

    def _get_opponents(self, stage_player, stage):
        opponents = []
        matches = Match.objects.filter(
            Q(player_one=stage_player) | Q(player_two=stage_player),
            round__stage=stage
        )

        for match in matches:
            if match.player_one == stage_player and match.player_two:
                opponents.append(match.player_two)
            elif match.player_two == stage_player:
                opponents.append(match.player_one)

        return opponents

    def is_descending(self):
        return True


class HeadToHeadRankingCriterion(RankingCriterion):
    def get_key(self):
        return 'head_to_head'

    def get_name(self):
        return 'H2H'

    def get_description(self):
        return 'Wins against tied opponents'

    def calculate_value(self, stage_player, stage, standings_cache=None):
        return 0

    def is_descending(self):
        return True


class SeedRankingCriterion(RankingCriterion):
    def get_key(self):
        return 'seed'

    def get_name(self):
        return 'Seed'

    def get_description(self):
        return 'Original tournament seed (lower is better)'

    def calculate_value(self, stage_player, stage, standings_cache=None):
        if standings_cache and stage_player.id in standings_cache:
            return standings_cache[stage_player.id].get('seed', 999)

        return stage_player.seed

    def is_descending(self):
        return False


class RandomRankingCriterion(RankingCriterion):
    def get_key(self):
        return 'random'

    def get_name(self):
        return 'Random'

    def get_description(self):
        return 'Random tiebreaker'

    def calculate_value(self, stage_player, stage, standings_cache=None):
        return random.random()

    def is_descending(self):
        return False


class PlayerScoreRankingCriterion(RankingCriterion):
    def get_key(self):
        return 'player_score'

    def get_name(self):
        return 'Player Score'

    def get_description(self):
        return 'Sum of player scores in current stage'

    def calculate_value(self, stage_player, stage, standings_cache=None):
        if standings_cache and stage_player.id in standings_cache:
            return standings_cache[stage_player.id].get('player_score', 0)

        player_one_score = MatchResult.objects.filter(
            match__round__stage=stage,
            match__player_one=stage_player
        ).aggregate(total=models.Sum('player_one_score'))['total'] or 0

        player_two_score = MatchResult.objects.filter(
            match__round__stage=stage,
            match__player_two=stage_player
        ).aggregate(total=models.Sum('player_two_score'))['total'] or 0

        return player_one_score + player_two_score

    def is_descending(self):
        return True


class OpponentScoreRankingCriterion(RankingCriterion):
    def get_key(self):
        return 'opponent_score'

    def get_name(self):
        return 'Opponent Score'

    def get_description(self):
        return 'Sum of opponent scores (lower is better)'

    def calculate_value(self, stage_player, stage, standings_cache=None):
        if standings_cache and stage_player.id in standings_cache:
            return standings_cache[stage_player.id].get('opponent_score', 0)

        opponent_score_as_player_one = MatchResult.objects.filter(
            match__round__stage=stage,
            match__player_one=stage_player
        ).aggregate(total=models.Sum('player_two_score'))['total'] or 0

        opponent_score_as_player_two = MatchResult.objects.filter(
            match__round__stage=stage,
            match__player_two=stage_player
        ).aggregate(total=models.Sum('player_one_score'))['total'] or 0

        return opponent_score_as_player_one + opponent_score_as_player_two

    def is_descending(self):
        return False


class ScoreDifferentialRankingCriterion(RankingCriterion):
    def get_key(self):
        return 'score_differential'

    def get_name(self):
        return 'Score Differential'

    def get_description(self):
        return 'Player score minus opponent score'

    def calculate_value(self, stage_player, stage, standings_cache=None):
        if standings_cache and stage_player.id in standings_cache:
            player_score = standings_cache[stage_player.id].get(
                'player_score', 0)
            opponent_score = standings_cache[stage_player.id].get(
                'opponent_score', 0)
            return player_score - opponent_score

        player_criterion = PlayerScoreRankingCriterion()
        opponent_criterion = OpponentScoreRankingCriterion()

        player_score = player_criterion.calculate_value(
            stage_player, stage, standings_cache)
        opponent_score = opponent_criterion.calculate_value(
            stage_player, stage, standings_cache)

        return player_score - opponent_score

    def is_descending(self):
        return True


class GamesPlayedRankingCriterion(RankingCriterion):
    def get_key(self):
        return 'games_played'

    def get_name(self):
        return 'Games Played'

    def get_description(self):
        return 'Total number of games played (higher is better)'

    def calculate_value(self, stage_player, stage, standings_cache=None):
        if standings_cache and stage_player.id in standings_cache:
            return standings_cache[stage_player.id].get('games_played', 0)

        return Match.objects.filter(
            Q(player_one=stage_player) | Q(player_two=stage_player),
            round__stage=stage
        ).count()

    def is_descending(self):
        return True


def get_available_ranking_criteria():
    return [
        WinsRankingCriterion(),
        LossesRankingCriterion(),
        PointsRankingCriterion(),
        StrengthOfScheduleRankingCriterion(),
        HeadToHeadRankingCriterion(),
        SeedRankingCriterion(),
        RandomRankingCriterion(),
        PlayerScoreRankingCriterion(),
        OpponentScoreRankingCriterion(),
        ScoreDifferentialRankingCriterion(),
        GamesPlayedRankingCriterion(),
    ]


def get_ranking_criterion_by_key(key):
    for criterion in get_available_ranking_criteria():
        if criterion.get_key() == key:
            return criterion
    return None


def get_default_main_stage_criteria():
    return [
        {'key': 'wins', 'enabled': True},
        {'key': 'strength_of_schedule', 'enabled': True},
        {'key': 'head_to_head', 'enabled': True},
        {'key': 'random', 'enabled': True},
    ]


def get_default_playoff_stage_criteria():
    return [
        {'key': 'wins', 'enabled': True},
        {'key': 'seed', 'enabled': True},
    ]


class Stage(models.Model):
    SCORE_REPORTING_DISABLED = 0
    SCORE_REPORTING_OPTIONAL = 1
    SCORE_REPORTING_REQUIRED = 2

    SCORE_REPORTING_CHOICES = [
        (SCORE_REPORTING_DISABLED, 'Disabled'),
        (SCORE_REPORTING_OPTIONAL, 'Optional'),
        (SCORE_REPORTING_REQUIRED, 'Required'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(default=None, null=True, blank=True)
    order = models.PositiveIntegerField(default=1)
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name='stages')
    pairing_strategy = models.CharField(max_length=50, default='swiss')
    max_players = models.PositiveIntegerField(
        default=None, null=True, blank=True)
    are_ties_allowed = models.BooleanField(default=False)
    report_full_scores = models.PositiveSmallIntegerField(
        choices=SCORE_REPORTING_CHOICES, default=SCORE_REPORTING_DISABLED)
    created_on = models.DateTimeField(auto_now_add=True)
    round_length_in_minutes = models.PositiveIntegerField(
        default=None, null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['tournament', 'order'],
                             name='unique_stage_order'),
        ]
        ordering = ['order']

    def __str__(self):
        return f'{self.tournament.name} - {self.name}'

    def is_complete(self):
        rounds = self.rounds.all()
        return rounds.exists() and all(round.is_complete() for round in rounds)

    def get_current_round(self):
        return self.rounds.order_by('-order').first()

    def get_pairing_strategy(self):
        return get_pairing_strategy(self.pairing_strategy)

    def get_ranking_criteria(self):
        criteria_qs = self.stage_ranking_criteria.all()

        if criteria_qs.exists():
            criteria_list = []
            available_keys = [c.get_key()
                              for c in get_available_ranking_criteria()]

            for criterion in criteria_qs:
                criteria_list.append(
                    {'key': criterion.criterion_key, 'enabled': True})

            for key in available_keys:
                if not any(c['key'] == key for c in criteria_list):
                    criteria_list.append({'key': key, 'enabled': False})

            return criteria_list
        else:
            if self.order == 1:
                return get_default_main_stage_criteria()
            else:
                return get_default_playoff_stage_criteria()

    def set_ranking_criteria(self, criteria_list):
        self.stage_ranking_criteria.all().delete()

        # Filter enabled criteria and sort by their order property
        enabled_criteria = [
            c for c in criteria_list if c.get('enabled', False)]
        enabled_criteria.sort(key=lambda x: x.get('order', 999))

        # Create StageRankingCriteria records with sequential order starting from 1
        for i, criterion in enumerate(enabled_criteria):
            StageRankingCriteria.objects.create(
                stage=self,
                criterion_key=criterion['key'],
                order=i + 1
            )

    def get_enabled_ranking_criteria_objects(self):
        criteria_list = self.stage_ranking_criteria.all()
        criteria_objects = []

        for criterion in criteria_list:
            criterion_obj = get_ranking_criterion_by_key(
                criterion.criterion_key)
            if criterion_obj:
                criteria_objects.append(criterion_obj)

        if not criteria_objects:
            if self.order == 1:
                default_criteria = get_default_main_stage_criteria()
            else:
                default_criteria = get_default_playoff_stage_criteria()

            for config in default_criteria:
                if config.get('enabled', True):
                    criterion = get_ranking_criterion_by_key(config['key'])
                    if criterion:
                        criteria_objects.append(criterion)

        return criteria_objects


class StageRankingCriteria(models.Model):
    stage = models.ForeignKey(
        Stage, on_delete=models.CASCADE, related_name='stage_ranking_criteria')
    criterion_key = models.CharField(max_length=50)
    order = models.PositiveIntegerField()

    class Meta:
        constraints = [
            UniqueConstraint(fields=['stage', 'criterion_key'],
                             name='unique_stage_criterion'),
            UniqueConstraint(fields=['stage', 'order'],
                             name='unique_stage_criterion_order'),
        ]
        ordering = ['order']

    def __str__(self):
        criterion = get_ranking_criterion_by_key(self.criterion_key)
        criterion_name = criterion.get_name() if criterion else self.criterion_key
        return f'{self.stage} - {criterion_name} (Order {self.order})'

    def get_criterion_object(self):
        return get_ranking_criterion_by_key(self.criterion_key)


class Group(models.Model):
    name = models.CharField(max_length=200)
    stage = models.ForeignKey(
        Stage, on_delete=models.CASCADE, related_name='groups')

    def __str__(self):
        return f'{self.stage.tournament.name} - {self.stage.name} - {self.name}'


class StagePlayer(models.Model):
    player = models.ForeignKey(

        Player, on_delete=models.CASCADE, related_name='stage_participations')
    stage = models.ForeignKey(
        Stage, on_delete=models.CASCADE, related_name='stage_players')
    seed = models.PositiveIntegerField()
    rank = models.PositiveIntegerField(default=None, null=True, blank=True)
    group = models.ForeignKey(
        Group, on_delete=models.SET_NULL, related_name='players',
        default=None, null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['player', 'stage'],
                             name='unique_stage_player'),
            UniqueConstraint(fields=['stage', 'seed'],
                             name='unique_stage_seed'),
        ]
        ordering = ['seed']

    def __str__(self):
        return f'{self.player.get_display_name()} (Seed {self.seed}) - {self.stage}'


class Round(models.Model):
    order = models.PositiveIntegerField(default=1)
    stage = models.ForeignKey(
        Stage, on_delete=models.CASCADE, related_name='rounds')
    created_on = models.DateTimeField(auto_now_add=True)
    round_length_in_minutes = models.PositiveIntegerField(
        default=None, null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['stage', 'order'],
                             name='unique_round_order'),
        ]
        ordering = ['order']

    def __str__(self):
        return f'{self.stage.tournament.name} - {self.stage.name} - Round {self.order}'

    def is_complete(self):
        return all(match.has_result() for match in self.matches.all())

    def get_end_timestamp(self):
        from datetime import timedelta
        if self.round_length_in_minutes:
            end_time = self.created_on + \
                timedelta(minutes=self.round_length_in_minutes)
            return int(end_time.timestamp() * 1000)
        return None


class Match(models.Model):
    round = models.ForeignKey(
        Round, on_delete=models.CASCADE, related_name='matches')
    player_one = models.ForeignKey(
        StagePlayer, on_delete=models.CASCADE, related_name='matches_as_player_one',
        default=None, null=True, blank=True)
    player_two = models.ForeignKey(
        StagePlayer, on_delete=models.CASCADE, related_name='matches_as_player_two',
        default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Matches'
        ordering = ['created_on']

    def __str__(self):
        if self.player_two is None:
            return f'{self.player_one.player.get_display_name()} (BYE) - {self.round}'
        return f'{self.player_one.player.get_display_name()} vs {self.player_two.player.get_display_name()} - {self.round}'

    def has_result(self):
        return hasattr(self, 'result')

    def is_bye(self):
        return self.player_two is None


class MatchResult(models.Model):
    match = models.OneToOneField(
        Match, on_delete=models.CASCADE, related_name='result')
    winner = models.ForeignKey(
        StagePlayer, on_delete=models.CASCADE, related_name='match_wins',
        default=None, null=True, blank=True)
    player_one_score = models.PositiveIntegerField(
        default=None, null=True, blank=True)
    player_two_score = models.PositiveIntegerField(
        default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.winner:
            return f'{self.winner.player.get_display_name()} wins - {self.match.round}'
        return f'Tie - {self.match.round}'

    def is_tie(self):
        return self.winner is None

    class Meta:
        ordering = ['created_on']


# Import the new pairing strategy system


class StandingCalculator:

    @staticmethod
    def get_stage_standings(stage):
        from django.db.models import Count, Q

        stage_players = stage.stage_players.all()
        if not stage_players:
            return []

        standings_cache = StandingCalculator._build_standings_cache(
            stage_players, stage)

        standings = []
        for stage_player in stage_players:
            standing_data = {
                'stage_player': stage_player,
                'wins': standings_cache[stage_player.id]['wins'],
                'losses': standings_cache[stage_player.id]['losses'],
                'byes': standings_cache[stage_player.id]['byes'],
                'ties': standings_cache[stage_player.id]['ties'],
                'points': standings_cache[stage_player.id]['points'],
                'total_matches': standings_cache[stage_player.id]['total_matches'],
                'strength_of_schedule': standings_cache[stage_player.id]['strength_of_schedule'],
                'seed': standings_cache[stage_player.id]['seed'],
            }
            standings.append(standing_data)

        criteria_objects = stage.get_enabled_ranking_criteria_objects()
        if not criteria_objects:
            criteria_objects = [
                PointsRankingCriterion(),
                WinsRankingCriterion(),
                StrengthOfScheduleRankingCriterion(),
                SeedRankingCriterion(),
            ]

        for criterion in criteria_objects:
            for standing in standings:
                key = criterion.get_key()
                standing[f'{key}_value'] = criterion.calculate_value(
                    standing['stage_player'], stage, standings_cache
                )

        def sort_key(standing):
            sort_values = []
            for criterion in criteria_objects:
                key = criterion.get_key()
                value = standing.get(f'{key}_value', 0)
                if criterion.is_descending():
                    sort_values.append(-value if isinstance(value,
                                       (int, float)) else value)
                else:
                    sort_values.append(value)
            return tuple(sort_values)

        standings.sort(key=sort_key)

        StandingCalculator._resolve_head_to_head_ties(
            standings, stage, criteria_objects)

        for i, standing in enumerate(standings):
            standing['rank'] = i + 1

        return standings

    @staticmethod
    def _build_standings_cache(stage_players, stage):
        from django.db.models import Count, Q

        cache = {}

        for stage_player in stage_players:
            wins = MatchResult.objects.filter(
                match__round__stage=stage,
                winner=stage_player
            ).count()

            byes = MatchResult.objects.filter(
                match__round__stage=stage,
                winner=stage_player,
                match__player_two__isnull=True
            ).count()

            total_matches = Match.objects.filter(
                Q(player_one=stage_player) | Q(player_two=stage_player),
                round__stage=stage
            ).count()

            losses = MatchResult.objects.filter(
                Q(match__player_one=stage_player) | Q(
                    match__player_two=stage_player),
                match__round__stage=stage
            ).exclude(winner=stage_player).exclude(winner=None).count()

            ties = MatchResult.objects.filter(
                Q(match__player_one=stage_player) | Q(
                    match__player_two=stage_player),
                match__round__stage=stage,
                winner=None
            ).count()

            points = wins * 2 + ties * 1

            opponents = StandingCalculator._get_opponents(stage_player, stage)
            strength_of_schedule = StandingCalculator._calculate_strength_of_schedule(
                opponents, stage)

            player_one_score = MatchResult.objects.filter(
                match__round__stage=stage,
                match__player_one=stage_player
            ).aggregate(total=models.Sum('player_one_score'))['total'] or 0

            player_two_score = MatchResult.objects.filter(
                match__round__stage=stage,
                match__player_two=stage_player
            ).aggregate(total=models.Sum('player_two_score'))['total'] or 0

            player_score = player_one_score + player_two_score

            opponent_score_as_player_one = MatchResult.objects.filter(
                match__round__stage=stage,
                match__player_one=stage_player
            ).aggregate(total=models.Sum('player_two_score'))['total'] or 0

            opponent_score_as_player_two = MatchResult.objects.filter(
                match__round__stage=stage,
                match__player_two=stage_player
            ).aggregate(total=models.Sum('player_one_score'))['total'] or 0

            opponent_score = opponent_score_as_player_one + opponent_score_as_player_two

            cache[stage_player.id] = {
                'wins': wins,
                'losses': losses,
                'ties': ties,
                'byes': byes,
                'points': points,
                'total_matches': total_matches,
                'games_played': total_matches,
                'strength_of_schedule': strength_of_schedule,
                'seed': stage_player.seed,
                'player_score': player_score,
                'opponent_score': opponent_score,
            }

        return cache

    @staticmethod
    def _resolve_head_to_head_ties(standings, stage, criteria_objects):
        has_head_to_head = any(
            c.get_key() == 'head_to_head' for c in criteria_objects)
        if not has_head_to_head:
            return

        i = 0
        while i < len(standings) - 1:
            tied_group = [standings[i]]
            j = i + 1

            while j < len(standings) and StandingCalculator._are_tied_before_head_to_head(
                standings[i], standings[j], criteria_objects
            ):
                tied_group.append(standings[j])
                j += 1

            if len(tied_group) > 1:
                head_to_head_results = StandingCalculator._calculate_head_to_head(
                    tied_group, stage)

                for standing in tied_group:
                    standing['head_to_head_value'] = head_to_head_results.get(
                        standing['stage_player'].id, 0)

                tied_group.sort(key=lambda x: head_to_head_results.get(
                    x['stage_player'].id, 0), reverse=True)

                for k, standing in enumerate(tied_group):
                    standings[i + k] = standing

            i = j

    @staticmethod
    def _are_tied_before_head_to_head(standing1, standing2, criteria_objects):
        for criterion in criteria_objects:
            if criterion.get_key() == 'head_to_head':
                return True

            key = criterion.get_key()
            val1 = standing1.get(f'{key}_value', 0)
            val2 = standing2.get(f'{key}_value', 0)

            if val1 != val2:
                return False

        return True

    @staticmethod
    def _calculate_head_to_head(tied_players, stage):
        results = {}

        for standing in tied_players:
            stage_player = standing['stage_player']
            wins = 0

            for other_standing in tied_players:
                if other_standing == standing:
                    continue

                other_stage_player = other_standing['stage_player']

                head_to_head_wins = MatchResult.objects.filter(
                    Q(match__player_one=stage_player, match__player_two=other_stage_player) |
                    Q(match__player_one=other_stage_player,
                      match__player_two=stage_player),
                    match__round__stage=stage,
                    winner=stage_player
                ).count()

                wins += head_to_head_wins

            results[stage_player.id] = wins

        return results

    @staticmethod
    def _get_opponents(stage_player, stage):
        opponents = []
        matches = Match.objects.filter(
            Q(player_one=stage_player) | Q(player_two=stage_player),
            round__stage=stage
        )

        for match in matches:
            if match.player_one == stage_player and match.player_two:
                opponents.append(match.player_two)
            elif match.player_two == stage_player:
                opponents.append(match.player_one)

        return opponents

    @staticmethod
    def _calculate_strength_of_schedule(opponents, stage):
        if not opponents:
            return 0

        total_opponent_points = 0
        for opponent in opponents:
            opponent_wins = MatchResult.objects.filter(
                match__round__stage=stage,
                winner=opponent
            ).count()

            opponent_ties = MatchResult.objects.filter(
                Q(match__player_one=opponent) | Q(match__player_two=opponent),
                match__round__stage=stage,
                winner=None
            ).count()

            total_opponent_points += (opponent_wins * 2 + opponent_ties * 1)

        return total_opponent_points / len(opponents) if opponents else 0

    @staticmethod
    def get_tournament_standings(tournament):
        """
        Get comprehensive tournament standings for all players registered.

        Logic:
        1. Players who advance to later stages rank ahead of those who didn't
        2. Active players rank ahead of dropped players
        3. Standing is determined by rank in highest stage achieved, or current live standings
        """
        from django.db.models import Count, Q, Max

        current_stage = tournament.get_current_stage()
        if not current_stage:
            return []

        # Get all players registered for the tournament
        all_players = tournament.players.all()
        if not all_players:
            return []

        # Get current stage standings first (properly sorted)
        current_standings = StandingCalculator.get_stage_standings(
            current_stage)

        # Build final standings starting with current stage players
        final_standings = []
        current_stage_player_ids = set()
        current_stage_active_players = []
        current_stage_dropped_players = []

        # First, separate current stage players into active and dropped
        for current_standing in current_standings:
            player = current_standing['stage_player'].player
            current_stage_player_ids.add(player.id)

            standing_data = {
                'player': player,
                'stage_player': current_standing['stage_player'],
                'highest_stage_order': current_stage.order,
                'is_active': player.status == Player.PlayerStatus.ACTIVE,
                'is_dropped': player.status == Player.PlayerStatus.DROPPED,
                'is_in_current_stage': True,
                'rank': current_standing['rank'],
                'wins': current_standing['wins'],
                'losses': current_standing['losses'],
                'byes': current_standing['byes'],
                'ties': current_standing['ties'],
                'points': current_standing['points'],
                'strength_of_schedule': current_standing['strength_of_schedule'],
                'seed': current_standing['seed'],
            }

            # Add criterion values for current stage
            for criterion in current_stage.get_enabled_ranking_criteria_objects():
                key = criterion.get_key()
                standing_data[f'{key}_value'] = current_standing.get(
                    f'{key}_value', None)

            # Separate into active and dropped lists while preserving order
            if player.status == Player.PlayerStatus.ACTIVE:
                current_stage_active_players.append(standing_data)
            else:
                current_stage_dropped_players.append(standing_data)

        # Add active players first, then dropped players
        final_standings.extend(current_stage_active_players)
        final_standings.extend(current_stage_dropped_players)

        # Then add players from other stages/not in current stage
        other_players = []
        for player in all_players:
            if player.id in current_stage_player_ids:
                continue  # Already added above

            # Find the highest stage this player achieved
            player_stages = StagePlayer.objects.filter(
                player=player,
                stage__tournament=tournament
            ).order_by('-stage__order')

            if not player_stages:
                continue

            highest_stage_player = player_stages.first()
            highest_stage = highest_stage_player.stage

            standing_data = {
                'player': player,
                'stage_player': highest_stage_player,
                'highest_stage_order': highest_stage.order,
                'is_active': player.status == Player.PlayerStatus.ACTIVE,
                'is_dropped': player.status == Player.PlayerStatus.DROPPED,
                'is_in_current_stage': False,
                'rank': highest_stage_player.rank or 999,
                'wins': None,
                'losses': None,
                'ties': None,
                'byes': None,
                'points': None,
                'strength_of_schedule': None,
                'seed': highest_stage_player.seed,
            }

            # Set criterion values to None (will show as dashes)
            for criterion in current_stage.get_enabled_ranking_criteria_objects():
                key = criterion.get_key()
                standing_data[f'{key}_value'] = None

            other_players.append(standing_data)

        # Sort other players by stage order (desc), active status, then rank
        other_players.sort(
            key=lambda x: (-x['highest_stage_order'], 0 if x['is_active'] else 1, x['rank']))
        final_standings.extend(other_players)

        # Assign final tournament ranks
        for i, standing in enumerate(final_standings):
            standing['tournament_rank'] = i + 1

        return final_standings


class TournamentActionLog(models.Model):
    class ActionType(models.TextChoices):
        CREATE_TOURNAMENT = 'create_tournament', _('Create Tournament')
        ADD_PLAYER = 'add_player', _('Add Player')
        DROP_PLAYER = 'drop_player', _('Drop Player')
        UNDROP_PLAYER = 'undrop_player', _('Undrop Player')
        CREATE_ROUND = 'create_round', _('Create Round')
        ADVANCE_STAGE = 'advance_stage', _('Advance Stage')
        REPORT_RESULT = 'report_result', _('Report Result')
        UPDATE_RESULT = 'update_result', _('Update Result')
        DELETE_ROUND = 'delete_round', _('Delete Round')
        REGISTER_PLAYER = 'register_player', _('Register Player')
        UNREGISTER_PLAYER = 'unregister_player', _('Unregister Player')

    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name='action_logs')
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name='tournament_actions', null=True, blank=True)
    action_type = models.CharField(max_length=20, choices=ActionType.choices)
    description = models.TextField(default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_on']

    def __str__(self):
        return f'{self.user.username} - {self.get_action_type_display()} - {self.tournament.name}'


class TournamentTimer(models.Model):
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name='tournament_timers')
    timer = models.OneToOneField(
        'timekeeper.CountdownTimer', on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_on']

    def __str__(self):
        return f'{self.tournament.name} - {self.timer.name}'
