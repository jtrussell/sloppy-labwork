from math import e
from os import name
from random import choice
from tabnanny import verbose
from django.db import models
from django.db.models import UniqueConstraint
from django.db.models import F
from datetime import date
from django.utils.translation import gettext_lazy as _


class Playgroup(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    events = models.ManyToManyField(
        'Event', through='PlaygroupEvent', related_name='playgroups'
    )

    class Meta:
        ordering = ['-name']

    def __str__(self):
        return self.name


class PlaygroupMember(models.Model):
    class FlairOptions(models.IntegerChoices):
        BROBNAR = (1, _('Brobnar'))
        DIS = (2, _('Dis'))
        EKWIDON = (3, _('Ekwidon'))
        GEISTOID = (4, _('Geistoid'))
        LOGOS = (5, _('Logos'))
        MARS = (6, _('Mars'))
        REDEMPTION = (7, _('Redemption'))
        SANCTUM = (8, _('Sanctum'))
        SAURIAN = (9, _('Saurian'))
        SHADOWS = (10, _('Shadows'))
        SKYBORN = (11, _('Skyborn'))
        STAR_ALLIANCE = (12, _('Star Alliance'))
        UNFATHOMABLE = (13, _('Unfathomable'))
        UNTAMED = (14, _('Untamed'))

    playgroup = models.ForeignKey(
        Playgroup, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    nickname = models.CharField(
        max_length=100, default=None, null=True, blank=True)
    joined_on = models.DateTimeField(auto_now_add=True)
    is_staff = models.BooleanField(default=False)
    house_flair = models.IntegerField(
        choices=FlairOptions.choices, default=None, null=True, blank=True)
    tagline = models.CharField(
        max_length=100, default=None, null=True, blank=True)

    # TODO - Add avatar and banner image fields to main user profile
    avatar_src = 'https://static.sloppylabwork.com/pmc/tmp/kc-logo-dark.png'
    banner_bg_color = '#131313'
    banner_stroke_color = '#ffb400'
    banner_text_color = '#fff'

    class Meta:
        constraints = [
            UniqueConstraint(fields=['playgroup', 'user'],
                             name='unique_playgroup_member'),
            UniqueConstraint(fields=['playgroup', 'nickname'],
                             name='unique_playgroup_member_nickname'),
        ]

    def __str__(self):
        return f'{self.nickname} ({self.user.username})' if self.nickname else self.user.username


class EventFormat(models.Model):
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class Event(models.Model):
    name = models.CharField(max_length=200)
    start_date = models.DateField(default=date.today)
    player_count = models.SmallIntegerField(
        default=None, null=True, blank=True)
    format = models.ForeignKey(EventFormat, on_delete=models.SET_NULL,
                               related_name='events', default=None, null=True, blank=True)

    class Meta:
        ordering = ('-start_date',)

    def get_player_count(self):
        return self.player_count or self.results.count()

    def __str__(self):
        return f'{self.name}'


class PlaygroupEvent(models.Model):
    playgroup = models.ForeignKey(
        Playgroup, on_delete=models.CASCADE, related_name='playgroup_events')
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name='playgroup_events')

    class Meta:
        unique_together = ('playgroup', 'event',)


class EventResult(models.Model):
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name='results')
    user = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE, related_name='event_results')
    finishing_position = models.PositiveSmallIntegerField(
        default=None, null=True, blank=True)
    num_wins = models.PositiveSmallIntegerField(
        default=None, null=True, blank=True)
    num_losses = models.PositiveSmallIntegerField(
        default=None, null=True, blank=True)

    class Meta:
        ordering = ('finishing_position', '-num_wins', 'num_losses',)

    def __str__(self):
        return f'{self.event.name} - {self.user} - ({self.finishing_position})'


class RankingPointsMap(models.Model):
    max_players = models.PositiveSmallIntegerField()
    finishing_position = models.PositiveSmallIntegerField()
    points = models.PositiveIntegerField()

    class Meta:
        ordering = ('max_players', 'finishing_position',)


class RankingPoints(models.Model):
    points = models.PositiveIntegerField(default=0)
    result = models.ForeignKey(
        EventResult, on_delete=models.CASCADE, related_name='ranking_points')
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = _('Ranking points')

    def __str__(self):
        return f'{self.points}'


class LeaderboardSeason(models.Model):
    name = models.CharField(max_length=200)
    sort_order = models.PositiveSmallIntegerField(default=1)


class LeaderboardSeasonPeriod(models.Model):
    class FrequencyOptions(models.IntegerChoices):
        MONTH = (1, _('Month'))
        SEASON = (2, _('Season'))
        ALL_TIME = (3, _('All Time'))

    name = models.CharField(max_length=200)
    start_date = models.DateField(default=date.today)
    season = models.ForeignKey(
        LeaderboardSeason, on_delete=models.CASCADE, related_name='periods')
    frequency = models.IntegerField(choices=FrequencyOptions.choices)

    class Meta:
        ordering = ('-start_date',)
        UniqueConstraint(fields=['start_date', 'frequency'],
                         name='unique_leaderboard_period')


class Leaderboard(models.Model):
    name = models.CharField(max_length=200)
    sort_order = models.PositiveSmallIntegerField(default=1)
    period_frequency = models.IntegerField(
        choices=LeaderboardSeasonPeriod.FrequencyOptions.choices)

    class Meta:
        ordering = ('sort_order',)

    def __str__(self):
        return self.name

    def get_start_and_end_of_current_period(self):
        today = date.today()
        if self.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.MONTH:
            return (today.replace(day=1), today)
        elif self.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.SEASON:
            # TODO - seasons should be anchored by KFC events
            return (today.replace(month=1, day=1), today)
        elif self.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.ALL_TIME:
            return (date(2020, 1, 1), today)
        else:
            raise ValueError(f'Unknown frequency: {self.period_frequency}')


class PlayerRank(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    rank = models.PositiveIntegerField()
    average_points = models.FloatField(default=0)
    leaderboard = models.ForeignKey(
        Leaderboard, on_delete=models.CASCADE, related_name='rankings')

    class Meta:
        ordering = ('rank',)
        constraints = [
            UniqueConstraint(
                fields=['user', 'leaderboard'], name='unique_player_rank'),
        ]


class PlayerRankHistory(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    rank = models.PositiveIntegerField()
    average_points = models.FloatField(default=0)
    leaderboard = models.ForeignKey(
        Leaderboard, on_delete=models.CASCADE, related_name='historic_rankings')
    period = models.ForeignKey(
        LeaderboardSeasonPeriod, on_delete=models.CASCADE)

    class Meta:
        ordering = ('rank',)
        constraints = [
            UniqueConstraint(
                fields=['user', 'leaderboard', 'period'], name='unique_player_rank_history'),
            # models.CheckConstraint(
            #     check=Q(leaderboard__period_frequency=F('period__frequency')),
            #     name='leaderboard_period_frequency_match'
            # )
        ]


class RankingPointsService():
    @staticmethod
    def assign_points_for_results(event_results, player_count):
        rp_map_entries = RankingPointsMap.objects.filter(
            max_players=RankingPointsMap.objects
            .filter(max_players__gte=player_count)
            .aggregate(models.Min('max_players'))['max_players__min']
        ).order_by('finishing_position')

        ranking_points = [RankingPoints(result=r)
                          for r in event_results if r.finishing_position]
        for rp in rp_map_entries:
            for pts in ranking_points:
                if int(pts.result.finishing_position) >= rp.finishing_position:
                    pts.points = rp.points

        RankingPoints.objects.bulk_create(ranking_points)
        return ranking_points

    @staticmethod
    def assign_points_for_event(event):
        results = event.results.all()
        RankingPoints.objects.filter(result__event=event).delete()
        return RankingPointsService.assign_points_for_results(
            results, event.player_count or len(results)
        )

    @staticmethod
    def assign_points_for_leaderboard(leaderboard, start_date, end_date, top_n=4):
        """
        Updates PlayerRank records based on the top N highest-scoring RankingPoints 
        within the given period.

        Args:
            leaderboard (Leaderboard): The leaderboard for which ranks are being calculated.
            start_date (date): The start date of the period.
            end_date (date): The end date of the period.
            top_n (int): The number of highest-scoring results to consider for each user.
        """

        from django.db.models import Subquery, OuterRef, Window, Sum
        from django.db.models.functions import Rank

        ranked_points = RankingPoints.objects.filter(
            result__event__start_date__gte=start_date,
            result__event__start_date__lt=end_date,
            result__user=OuterRef("result__user")
        ).order_by("-points").values("points")[:top_n]

        user_points = (
            RankingPoints.objects.filter(
                result__event__start_date__gte=start_date,
                result__event__start_date__lt=end_date
            )
            .filter(points__in=Subquery(ranked_points))
            .values(user_id=F("result__user"))
            .annotate(avg_points=Sum("points") / top_n)
            .annotate(
                rank=Window(
                    expression=Rank(),
                    order_by=[F("avg_points").desc()]
                )
            )
        )

        player_ranks = [
            PlayerRank(
                user_id=entry["user_id"],
                rank=entry["rank"],
                average_points=entry["avg_points"],
                leaderboard=leaderboard
            )
            for entry in user_points
        ]
        PlayerRank.objects.filter(leaderboard=leaderboard).delete()
        PlayerRank.objects.bulk_create(player_ranks, ignore_conflicts=True)
        # return player_ranks
