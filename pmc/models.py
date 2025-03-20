from colorama import Back
from django.contrib.auth.models import User
from django.db import models
from django.db.models import UniqueConstraint
from datetime import date
from datetime import timedelta
from django.utils.translation import gettext_lazy as _
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db.models import Sum, Value, F, Count, Window
from django.db.models.functions import Coalesce, Rank
from django.conf import settings
from io import BytesIO
import qrcode
import boto3
import hashlib


class Playgroup(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    logo_src = models.URLField(default=None, null=True, blank=True)
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
    playgroup = models.ForeignKey(
        Playgroup, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    nickname = models.CharField(
        max_length=100, default=None, null=True, blank=True)
    joined_on = models.DateTimeField(auto_now_add=True)
    is_staff = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['playgroup', 'user'],
                             name='unique_playgroup_member'),
            UniqueConstraint(fields=['playgroup', 'nickname'],
                             name='unique_playgroup_member_nickname'),
        ]

    def __str__(self):
        return f'{self.nickname} ({self.user.username})' if self.nickname else self.user.username

    def get_events(self):
        return self.user.event_results.filter(
            event__playgroups=self.playgroup
        ).order_by('-event__start_date')

    def get_events_won(self):
        return self.get_events().filter(finishing_position=1)

    def get_num_match_wins(self):
        return self.get_events().aggregate(Sum('num_wins'))['num_wins__sum'] or 0


class EventFormat(models.Model):
    name = models.CharField(max_length=200, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ('sort_order', 'name',)

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
    xp_for_attendance = 25
    xp_for_win = 10
    xp_for_loss = 5

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

    def get_xp(self):
        xp = self.xp_for_attendance
        if self.num_wins:
            xp += self.num_wins * self.xp_for_win
        if self.num_losses:
            xp += self.num_losses * self.xp_for_loss
        return xp


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
    name = models.CharField(max_length=200, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ('sort_order', 'name',)

    def __str__(self):
        return self.name


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

    def __str__(self):
        return f'{self.name}'


class Leaderboard(models.Model):
    name = models.CharField(max_length=200)
    sort_order = models.PositiveSmallIntegerField(default=1)
    period_frequency = models.IntegerField(
        choices=LeaderboardSeasonPeriod.FrequencyOptions.choices)

    class Meta:
        ordering = ('sort_order',)

    def __str__(self):
        return self.name

    def get_current_period(self):
        return LeaderboardSeasonPeriod.objects.filter(
            frequency=self.period_frequency
        ).order_by('-start_date').first()

    def get_period_for_date(self, the_date):
        if self.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.ALL_TIME:
            return LeaderboardSeasonPeriod.objects.filter(
                frequency=self.period_frequency
            ).first()

        # Seasons start on December 1st
        december = 12
        if the_date.month == december:
            season_name = f'{the_date.year} - {the_date.year + 1}'
        else:
            season_name = f'{the_date.year - 1} - {the_date.year}'
        season, _ = LeaderboardSeason.objects.get_or_create(name=season_name)

        if self.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.MONTH:
            period_start = the_date.replace(day=1)
            period_name = period_start.strftime('%B %Y')
        elif self.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.SEASON:
            period_name = season_name
            if the_date.month == december:
                period_start = the_date.replace(day=1)
            else:
                period_start = the_date.replace(
                    year=the_date.year - 1, month=december, day=1)
        else:
            raise ValueError(
                f'Unhandled leaderboard period frequency {self.period_frequency}')

        period, _ = LeaderboardSeasonPeriod.objects.get_or_create(
            name=period_name,
            start_date=period_start,
            season=season,
            frequency=self.period_frequency
        )

        return period


class PlayerRank(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    playgroup = models.ForeignKey(
        Playgroup, on_delete=models.CASCADE, default=None, null=True, blank=True)
    rank = models.PositiveIntegerField()
    average_points = models.FloatField(default=0)
    num_results = models.PositiveIntegerField(default=0)
    total_points = models.FloatField(default=0)
    leaderboard = models.ForeignKey(
        Leaderboard, on_delete=models.CASCADE, related_name='rankings')
    period = models.ForeignKey(
        LeaderboardSeasonPeriod, on_delete=models.CASCADE)

    class Meta:
        ordering = ('rank', '-num_results')
        constraints = [
            UniqueConstraint(
                fields=['user', 'leaderboard', 'playgroup', 'period'], name='unique_user_leaderboard_playgroup_period'),
        ]


class LevelBreakpoint(models.Model):
    level = models.PositiveIntegerField(unique=True)
    required_xp = models.PositiveIntegerField()

    class Meta:
        ordering = ('level',)

    def __str__(self):
        return f'{self.level}'


class PmcProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='pmc_profile')
    avatar = models.ForeignKey(
        'Avatar', on_delete=models.SET_NULL, default=None, null=True, blank=True)
    background = models.ForeignKey(
        'Background', on_delete=models.SET_NULL, default=None, null=True, blank=True)
    tagline = models.CharField(
        max_length=100, default=None, null=True, blank=True)
    mv_id = models.CharField(max_length=36, unique=True,
                             default=None, null=True, blank=True)
    mv_username = models.CharField(
        max_length=100, default=None, null=True, blank=True)
    mv_qrcode_message = models.CharField(
        max_length=200, default=None, null=True, blank=True)

    def get_avatar(self):
        try:
            return self.avatar or Avatar.objects.get(pmc_id='001')
        except Avatar.DoesNotExist:
            return None

    def get_background(self):
        try:
            return self.background or Background.objects.get(pmc_id='001')
        except Background.DoesNotExist:
            return None

    def get_events(self):
        return self.user.event_results.order_by('-event__start_date')

    def get_events_won(self):
        return self.get_events().filter(finishing_position=1)

    def get_num_match_wins(self):
        return self.get_events().aggregate(Sum('num_wins'))['num_wins__sum'] or 0

    def get_total_xp(self):
        experience_points = (
            EventResult.objects.filter(user=self.user)
            .annotate(
                attendance_points=Value(EventResult.xp_for_attendance),
                win_points=Coalesce(F('num_wins'), 0) * EventResult.xp_for_win,
                loss_points=Coalesce(F('num_losses'), 0) *
                EventResult.xp_for_loss
            )
            .aggregate(
                total_experience=Sum(
                    F('attendance_points') + F('win_points') + F('loss_points'))
            )
        )
        return experience_points["total_experience"] or 0

    def get_level(self):
        return LevelBreakpoint.objects.filter(
            required_xp__lte=self.get_total_xp()
        ).order_by('-level').first()

    def get_next_level(self):
        return LevelBreakpoint.objects.filter(
            required_xp__gt=self.get_total_xp()
        ).order_by('level').first()

    def _get_level_up_info(self):
        total_xp = self.get_total_xp()
        current_level = self.get_level()
        next_level = self.get_next_level()

        percent_level_up = None
        if current_level and next_level:
            level_increment = next_level.required_xp - current_level.required_xp
            level_increment_progress = total_xp - current_level.required_xp
            if level_increment > 0:
                percent_level_up = round(
                    100 * (level_increment_progress) / (level_increment))
        else:
            level_increment = None
            level_increment_progress = None
        return {
            'current_level': current_level,
            'next_level': next_level,
            'total_xp': total_xp,
            'percent_level_up': percent_level_up,
            'level_increment': level_increment,
            'level_increment_progress': level_increment_progress,
        }

    def get_percent_level_up(self):
        return self._get_level_up_info()['percent_level_up']

    def get_level_increment(self):
        return self._get_level_up_info()['level_increment']

    def get_level_increment_progress(self):
        return self._get_level_up_info()['level_increment_progress']

    def get_mv_qrcode_path(self):
        if not self.mv_qrcode_message:
            return None
        hash = hashlib.md5(self.mv_qrcode_message.encode()).hexdigest()
        return f'mv-qrcode/{hash}.png'

    def save_qrcode(self):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        qr.add_data(self.mv_qrcode_message)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')

        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        s3_client = boto3.client('s3')
        bucket_name = settings.AWS_S3_BUCKET_MV_QRCODE
        s3_key = self.get_mv_qrcode_path()
        s3_client.upload_fileobj(
            buffer,
            bucket_name,
            s3_key,
            ExtraArgs={'ContentType': 'image/png', 'ACL': 'public-read'}
        )


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created or not hasattr(instance, 'pmc_profile'):
        PmcProfile.objects.create(user=instance)
    else:
        instance.pmc_profile.save()


class LeaderboardLog(models.Model):
    class ActionOptions(models.IntegerChoices):
        UPDATE = (1, _('Update Rankings'))
    leaderboard = models.ForeignKey(Leaderboard, on_delete=models.CASCADE)
    action = models.IntegerField(
        choices=ActionOptions.choices, default=ActionOptions.UPDATE)
    action_date = models.DateTimeField(auto_now_add=True)


class RankingPointsService():
    @staticmethod
    def assign_points_for_results(event_results, player_count):
        rp_map_entries = RankingPointsMap.objects.filter(
            max_players=RankingPointsMap.objects
            .filter(max_players__gte=player_count)
            .aggregate(models.Min('max_players'))['max_players__min']
        ).order_by('finishing_position')

        ranking_points = [RankingPoints(result=r, points=0)
                          for r in event_results]
        for rp in rp_map_entries:
            for pts in ranking_points:
                if int(pts.result.finishing_position or 0) >= rp.finishing_position:
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
    def assign_points_for_leaderboard(leaderboard, ranking_period, order_by='total_points', top_n=4):
        """
        Updates PlayerRank records based on the top N highest-scoring RankingPoints
        within a given ranking period. Computes both global and playgroup rankings.

        Args:
            leaderboard (Leaderboard): The leaderboard for which ranks are being calculated.
            ranking_period (LeaderboardSeasonPeriod): The period defining the date range.
            top_n (int): The number of highest-scoring results to consider for calculating average points.
        """

        start_date = ranking_period.start_date
        next_period = LeaderboardSeasonPeriod.objects.filter(
            frequency=ranking_period.frequency,
            start_date__gt=start_date
        ).order_by("start_date").first()
        tomorrow = date.today() + timedelta(days=1)
        end_date = next_period.start_date if next_period else tomorrow

        ranking_points_qs = RankingPoints.objects.filter(
            result__event__start_date__gte=start_date,
            result__event__start_date__lt=end_date
        )

        ranked_points = ranking_points_qs.annotate(
            point_rank=Window(
                expression=Rank(),
                partition_by=[F("result__user")],
                order_by=F("points").desc()
            )
        ).filter(point_rank__lte=top_n)

        def compute_rankings(playgroup=None):
            """ Helper function to compute rankings for a given playgroup or globally. """
            filters = {}
            if playgroup:
                filters["result__event__playgroups"] = playgroup

            all_user_points = ranking_points_qs.filter(**filters).values("result__user").annotate(
                total_points=Sum("points"),
                num_results=Count("id")
            )

            top_n_user_points = ranked_points.filter(**filters).values("result__user").annotate(
                avg_points=Sum("points") / top_n
            )

            user_data = {entry["result__user"]: entry for entry in all_user_points}
            for entry in top_n_user_points:
                if entry["result__user"] in user_data:
                    user_data[entry["result__user"]
                              ]["avg_points"] = entry["avg_points"]

            player_ranks = [
                PlayerRank(
                    user_id=user_id,
                    playgroup=playgroup,
                    rank=None,
                    average_points=user_data[user_id].get("avg_points", 0),
                    total_points=user_data[user_id]["total_points"],
                    num_results=user_data[user_id]["num_results"],
                    leaderboard=leaderboard,
                    period=ranking_period
                )
                for user_id in user_data
            ]

            player_ranks.sort(
                key=lambda pr: (-getattr(pr, order_by), -pr.num_results))
            for rank, pr in enumerate(player_ranks, start=1):
                pr.rank = rank

            return player_ranks

        global_ranks = compute_rankings(playgroup=None)
        playgroup_ranks = []
        for playgroup in Playgroup.objects.all():
            playgroup_ranks.extend(compute_rankings(playgroup=playgroup))

        PlayerRank.objects.filter(
            leaderboard=leaderboard, period=ranking_period).delete()
        PlayerRank.objects.bulk_create(
            global_ranks + playgroup_ranks, ignore_conflicts=True)

        return global_ranks + playgroup_ranks


class Avatar(models.Model):
    pmc_id = models.CharField(max_length=10, unique=True)
    src = models.URLField()
    category_label = models.CharField(max_length=25)
    name = models.CharField(max_length=100)
    banner_bg_color = models.CharField(max_length=6)
    banner_stroke_color = models.CharField(max_length=6)
    required_level = models.PositiveIntegerField(default=0)

    @property
    def banner_text_color(self):
        hex_color = self.banner_bg_color
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        brightness = int(0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])
        return '000' if brightness > 128 else 'fff'

    class Meta:
        ordering = ('required_level', 'pmc_id')

    def __str__(self):
        return self.name


class Background(models.Model):
    pmc_id = models.CharField(max_length=10, unique=True)
    src = models.URLField()
    category_label = models.CharField(max_length=25)
    name = models.CharField(max_length=100)
    required_level = models.PositiveIntegerField(default=0)
    artist_credit = models.CharField(
        max_length=100, default=None, null=True, blank=True)

    class Meta:
        ordering = ('required_level', 'pmc_id')

    def __str__(self):
        return self.name
