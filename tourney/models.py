from enum import unique
from django.contrib.auth.models import User
from django.db import models
from django.db.models import UniqueConstraint
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
import random
from abc import ABC, abstractmethod


class Tournament(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(default=None, null=True, blank=True)
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='owned_tournaments')
    is_accepting_registrations = models.BooleanField(default=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_on']

    def __str__(self):
        return self.name

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

    def create_initial_stage(self, main_pairing_strategy='swiss', main_max_players=None):
        if not self.stages.exists():
            stage = Stage.objects.create(
                tournament=self,
                name='Main Stage',
                order=1,
                pairing_strategy=main_pairing_strategy,
                max_players=main_max_players
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

    def create_playoff_stage(self, max_players=8):
        if self.stages.filter(order=2).exists():
            return self.stages.get(order=2)

        stage = Stage.objects.create(
            tournament=self,
            name='Playoff Stage',
            order=2,
            pairing_strategy='single_elimination',
            max_players=max_players
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

    def advance_to_next_stage(self):
        """
        Advances tournament to the next stage by seeding players based on 
        current standings and creating the first round.
        """
        current_stage = self.get_current_stage()
        next_stage = self.get_next_stage()

        if not self.can_start_next_stage():
            raise ValueError("Cannot advance to next stage at this time")

        # Get current standings from the current stage
        standings = StandingCalculator.get_stage_standings(current_stage)

        # Take top players up to max_players limit of next stage
        max_players = next_stage.max_players or len(standings)
        top_standings = standings[:max_players]

        # Create stage players with proper seeding
        for i, standing in enumerate(top_standings):
            StagePlayer.objects.create(
                player=standing['stage_player'].player,
                stage=next_stage,
                seed=i + 1  # Seed 1 for 1st place, seed 2 for 2nd place, etc.
            )

        # Create first round in next stage
        pairing_strategy = get_pairing_strategy(next_stage.pairing_strategy)

        next_order = (next_stage.rounds.aggregate(
            models.Max('order'))['order__max'] or 0) + 1
        new_round = Round.objects.create(stage=next_stage, order=next_order)

        pairing_strategy.make_pairings_for_round(new_round)

        return next_stage


class Player(models.Model):
    class PlayerStatus(models.TextChoices):
        ACTIVE = 'active', _('Active')
        DROPPED = 'dropped', _('Dropped')

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='tournament_players',
        null=True, blank=True, help_text="Leave empty for guest players")
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name='players')
    status = models.CharField(
        max_length=10, choices=PlayerStatus.choices, default=PlayerStatus.ACTIVE)
    nickname = models.CharField(
        max_length=100, default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)

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
        User, on_delete=models.CASCADE, related_name='tournament_admin_roles')
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
        return 'Strength of Schedule'

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
        return 'Head-to-Head'

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


def get_available_ranking_criteria():
    return [
        WinsRankingCriterion(),
        LossesRankingCriterion(),
        PointsRankingCriterion(),
        StrengthOfScheduleRankingCriterion(),
        HeadToHeadRankingCriterion(),
        SeedRankingCriterion(),
        RandomRankingCriterion(),
    ]


def get_ranking_criterion_by_key(key):
    for criterion in get_available_ranking_criteria():
        if criterion.get_key() == key:
            return criterion
    return None


def get_default_main_stage_criteria():
    return [
        {'key': 'points', 'enabled': True},
        {'key': 'wins', 'enabled': True},
        {'key': 'strength_of_schedule', 'enabled': True},
        {'key': 'seed', 'enabled': True},
    ]


def get_default_playoff_stage_criteria():
    return [
        {'key': 'wins', 'enabled': True},
        {'key': 'seed', 'enabled': True},
    ]


class Stage(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(default=None, null=True, blank=True)
    order = models.PositiveIntegerField(default=1)
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name='stages')
    pairing_strategy = models.CharField(max_length=50, default='swiss')
    max_players = models.PositiveIntegerField(
        default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)

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

    def get_ranking_criteria(self):
        criteria_qs = self.stage_ranking_criteria.all()
        
        if criteria_qs.exists():
            criteria_list = []
            available_keys = [c.get_key() for c in get_available_ranking_criteria()]
            
            for criterion in criteria_qs:
                criteria_list.append({'key': criterion.criterion_key, 'enabled': True})
            
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
        enabled_criteria = [c for c in criteria_list if c.get('enabled', False)]
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
            criterion_obj = get_ranking_criterion_by_key(criterion.criterion_key)
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
        unique


class PairingStrategy:
    def make_pairings_for_round(self, round):
        raise NotImplementedError(
            "Subclasses must implement make_pairings_for_round")

    def can_create_new_round(self, stage):
        current_round = stage.get_current_round()
        return current_round is None or current_round.is_complete()


class SwissPairingStrategy(PairingStrategy):
    def make_pairings_for_round(self, round):
        stage = round.stage
        stage_players = list(stage.stage_players.filter(
            player__status=Player.PlayerStatus.ACTIVE))

        if round.order == 1:
            import random
            random.shuffle(stage_players)
        else:
            stage_players = self._get_sorted_players_by_standings(stage)

        matches = []
        paired_players = set()

        for i in range(0, len(stage_players), 2):
            if i + 1 < len(stage_players):
                player_one = stage_players[i]
                player_two = stage_players[i + 1]

                if player_one.id not in paired_players and player_two.id not in paired_players:
                    match = Match(
                        round=round,
                        player_one=player_one,
                        player_two=player_two
                    )
                    matches.append(match)
                    paired_players.add(player_one.id)
                    paired_players.add(player_two.id)
            else:
                if stage_players[i].id not in paired_players:
                    bye_match = Match(
                        round=round,
                        player_one=stage_players[i],
                        player_two=None
                    )
                    matches.append(bye_match)
                    paired_players.add(stage_players[i].id)

        Match.objects.bulk_create(matches)

        for match in matches:
            if match.is_bye():
                MatchResult.objects.create(
                    match=match,
                    winner=match.player_one
                )

    def _get_sorted_players_by_standings(self, stage):

        players_with_stats = []
        for stage_player in stage.stage_players.filter(player__status=Player.PlayerStatus.ACTIVE):
            wins = MatchResult.objects.filter(
                match__round__stage=stage,
                winner=stage_player
            ).count()

            losses = MatchResult.objects.filter(
                Q(match__player_one=stage_player) | Q(
                    match__player_two=stage_player),
                match__round__stage=stage
            ).exclude(winner=stage_player).exclude(winner=None).count()

            players_with_stats.append((stage_player, wins, losses))

        players_with_stats.sort(key=lambda x: (-x[1], x[2], x[0].seed))
        return [player for player, wins, losses in players_with_stats]


class SingleEliminationPairingStrategy(PairingStrategy):
    def make_pairings_for_round(self, round):
        stage = round.stage

        if round.order == 1:
            stage_players = list(stage.stage_players.filter(
                player__status=Player.PlayerStatus.ACTIVE).order_by('seed'))
        else:
            stage_players = self._get_winners_from_previous_round(stage, round)

        matches = []
        for i in range(0, len(stage_players), 2):
            if i + 1 < len(stage_players):
                match = Match(
                    round=round,
                    player_one=stage_players[i],
                    player_two=stage_players[i + 1]
                )
                matches.append(match)
            else:
                bye_match = Match(
                    round=round,
                    player_one=stage_players[i],
                    player_two=None
                )
                matches.append(bye_match)

        Match.objects.bulk_create(matches)

        for match in matches:
            if match.is_bye():
                MatchResult.objects.create(
                    match=match,
                    winner=match.player_one
                )

    def _get_winners_from_previous_round(self, stage, current_round):
        previous_round = stage.rounds.filter(
            order=current_round.order - 1).first()
        if not previous_round:
            return []

        winners = []
        for match in previous_round.matches.all():
            if match.has_result() and match.result.winner:
                winners.append(match.result.winner)

        return winners

    def can_create_new_round(self, stage):
        if not super().can_create_new_round(stage):
            return False

        current_round = stage.get_current_round()
        if current_round:
            completed_matches = current_round.matches.filter(
                result__isnull=False).count()
            if completed_matches <= 1:
                return False

        return True


class RoundRobinSelfScheduledPairingStrategy(PairingStrategy):
    def make_pairings_for_round(self, round):
        pass

    def can_create_new_round(self, stage):
        return False


PAIRING_STRATEGIES = {
    'swiss': SwissPairingStrategy,
    'single_elimination': SingleEliminationPairingStrategy,
    'round_robin': RoundRobinSelfScheduledPairingStrategy,
}


def get_pairing_strategy(strategy_name):
    strategy_class = PAIRING_STRATEGIES.get(strategy_name)
    if strategy_class:
        return strategy_class()
    raise ValueError(f"Unknown pairing strategy: {strategy_name}")


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

            cache[stage_player.id] = {
                'wins': wins,
                'losses': losses,
                'ties': ties,
                'points': points,
                'total_matches': total_matches,
                'strength_of_schedule': strength_of_schedule,
                'seed': stage_player.seed,
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
        User, on_delete=models.CASCADE, related_name='tournament_actions')
    action_type = models.CharField(max_length=20, choices=ActionType.choices)
    description = models.TextField(default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_on']

    def __str__(self):
        return f'{self.user.username} - {self.get_action_type_display()} - {self.tournament.name}'
