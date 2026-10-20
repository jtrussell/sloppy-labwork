from sre_constants import ANY
from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Q, UniqueConstraint, OuterRef, Subquery, Exists
from datetime import date
from datetime import timedelta
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from contextlib import contextmanager
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db.models import Sum, F, Count, Window, Value, Func
from django.db.models.functions import Cast, Coalesce, Rank
from django.db.models.lookups import GreaterThan
from django.conf import settings
from io import BytesIO
from collections import namedtuple
import qrcode
import boto3
import hashlib
from decks.models import Deck


def exclude_upcoming_event_results(qs):
    from pmc.models import EventResult
    has_finished_result = Exists(
        EventResult.objects.filter(
            event_id=OuterRef('event_id'),
            finishing_position__isnull=False,
        )
    )
    cutoff = date.today() - timedelta(days=1)
    return qs.filter(
        Q(event__start_date__lt=cutoff) | has_finished_result
    )


def filter_upcoming_events(qs):
    from pmc.models import EventResult
    cutoff = date.today() - timedelta(days=1)
    has_finished_result = Exists(
        EventResult.objects.filter(
            event_id=OuterRef('pk'),
            finishing_position__isnull=False,
        )
    )
    return qs.filter(start_date__gte=cutoff).exclude(has_finished_result)


def count_subquery(qs):
    counted = qs.order_by().annotate(
        row_count=Func(F('pk'), function='COUNT')
    ).values('row_count')
    return Coalesce(Subquery(counted), Value(0))


ActivityLevel = namedtuple(
    'ActivityLevel', ['min_events', 'slug', 'label', 'filled_segments'])

ACTIVITY_LEVELS = (
    ActivityLevel(9, 'blazing', _('Blazing'), 3),
    ActivityLevel(4, 'busy', _('Busy'), 2),
    ActivityLevel(1, 'active', _('Active'), 1),
)


def get_activity_level(event_count):
    return next(
        (level for level in ACTIVITY_LEVELS if event_count >= level.min_events),
        None,
    )


class PlaygroupQuerySet(models.QuerySet):
    UNFORMATTED_EVENT_FORMAT = 'other'
    RECENT_ACTIVITY_WINDOW = timedelta(days=365)
    ACTIVITY_WINDOW = timedelta(days=90)

    def discoverable(self):
        return self.filter(is_global=False)

    def with_mappable_venues(self):
        return self.filter(Exists(
            Venue.objects.filter(playgroups=OuterRef('pk')).mappable()
        ))

    def matching_search(self, search_term, mappable_venues_only=False):
        matching_venues = Venue.objects.filter(
            Q(playgroups=OuterRef('pk')) & (
                Q(name__icontains=search_term) |
                Q(city__icontains=search_term) |
                Q(state_province__icontains=search_term) |
                Q(country__icontains=search_term)
            )
        )
        if mappable_venues_only:
            matching_venues = matching_venues.mappable()
        return self.filter(
            Q(name__icontains=search_term) | Exists(matching_venues)
        )

    @classmethod
    def filter_events_by_format(cls, events, event_format):
        if event_format == cls.UNFORMATTED_EVENT_FORMAT:
            return events.filter(format__isnull=True)
        if event_format:
            return events.filter(format_id=event_format)
        return events

    def hosting_events(self, event_format=None, upcoming_only=False, is_digital=None):
        matching_events = Event.objects.filter(playgroups=OuterRef('pk'))

        if is_digital is not None:
            matching_events = matching_events.filter(is_digital=is_digital)

        matching_events = self.filter_events_by_format(
            matching_events, event_format)

        if upcoming_only:
            matching_events = filter_upcoming_events(matching_events)
        else:
            matching_events = matching_events.filter(
                start_date__gte=date.today() - self.RECENT_ACTIVITY_WINDOW)

        return self.filter(Exists(matching_events))

    def located_in(self, country, region=None):
        matching_venues = Venue.objects.filter(
            playgroups=OuterRef('pk'), country=country)
        if region:
            matching_venues = matching_venues.filter(state_province=region)
        return self.filter(Exists(matching_venues))

    def annotate_member_count(self):
        return self.annotate(member_count=count_subquery(
            PlaygroupMember.objects.filter(playgroup=OuterRef('pk'))
        ))

    def annotate_is_primarily_digital(self):
        share_of_recent_events_digital = Func(
            Cast('is_digital', models.IntegerField()), function='AVG')
        digital_majority_or_default = Event.objects.filter(
            playgroups=OuterRef('pk'),
            start_date__gte=date.today() - self.RECENT_ACTIVITY_WINDOW,
        ).order_by().annotate(
            is_digital_majority=Coalesce(
                GreaterThan(share_of_recent_events_digital, Value(0.5)),
                OuterRef('event_default_is_digital'),
                output_field=models.BooleanField(),
            )
        ).values('is_digital_majority')
        return self.annotate(is_primarily_digital=Subquery(
            digital_majority_or_default, output_field=models.BooleanField()))

    def annotate_next_upcoming_event(self, is_digital=None, event_format=None):
        upcoming_events = filter_upcoming_events(
            Event.objects.filter(playgroups=OuterRef('pk')))
        if is_digital is not None:
            upcoming_events = upcoming_events.filter(is_digital=is_digital)
        upcoming_events = self.filter_events_by_format(
            upcoming_events, event_format)
        upcoming_events = upcoming_events.order_by('start_date', 'pk')
        return self.annotate(
            next_event_date=Subquery(
                upcoming_events.values('start_date')[:1]),
            next_event_format_name=Subquery(
                upcoming_events.values('format__name')[:1]),
        )

    def annotate_recent_activity(self):
        recent_events = Event.objects.filter(
            playgroups=OuterRef('pk'),
            start_date__gte=date.today() - self.ACTIVITY_WINDOW,
            start_date__lte=date.today(),
        )
        held_events = Event.objects.filter(
            playgroups=OuterRef('pk'),
            start_date__lte=date.today(),
        ).order_by('-start_date')
        return self.annotate(
            events_last_90_days=count_subquery(recent_events),
            last_event_date=Subquery(held_events.values('start_date')[:1]),
        )


class VenueQuerySet(models.QuerySet):
    def mappable(self):
        return self.filter(latitude__isnull=False, longitude__isnull=False)

    def used_by_discoverable_playgroups(self):
        return self.filter(playgroups__is_global=False).distinct()


class PlaygroupType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(
        max_length=200, default='## Welcome!\n\nEOs may customize this space.', null=True, blank=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class Playgroup(models.Model):
    name = models.CharField(max_length=200)
    type = models.ForeignKey(
        PlaygroupType, on_delete=models.SET_NULL, related_name='playgroups', default=None, null=True, blank=True)
    slug = models.SlugField(max_length=100, unique=True)
    logo_src = models.URLField(default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    events = models.ManyToManyField(
        'Event', through='PlaygroupEvent', related_name='playgroups'
    )
    venues = models.ManyToManyField(
        'Venue', through='PlaygroupVenue', related_name='playgroups'
    )
    primary_venue = models.ForeignKey(
        'Venue', on_delete=models.SET_NULL,
        default=None, null=True, blank=True,
        related_name='primary_for_playgroups'
    )
    description = models.TextField(default=None, null=True, blank=True)
    is_global = models.BooleanField(default=False)
    event_default_is_digital = models.BooleanField(
        default=False,
        verbose_name=_('Default Mode'),
        help_text=_(
            'Should new events in this group default to online or in-person?')
    )

    objects = PlaygroupQuerySet.as_manager()

    class Meta:
        ordering = ['-name']

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.primary_venue_id and self.pk:
            if not self.venues.filter(pk=self.primary_venue_id).exists():
                raise ValidationError({
                    'primary_venue': _('Primary venue must be one of the playgroup\'s linked venues.')
                })

    def get_logo_src(self):
        return self.logo_src or 'https://res.cloudinary.com/dig7eguxo/image/upload/v1743023566/Playgroup_yis2hs.svg'

    def get_pending_join_requests(self):
        return self.join_requests.filter(
            status=PlaygroupJoinRequest.RequestStatuses.SUBMITTED).order_by('-created_on')

    def get_staff_email_list(self):
        return self.members.filter(is_staff=True).values_list('user__email', flat=True)

    def get_enabled_feature_keys(self):
        override_by_key = dict(
            self.feature_overrides.values_list('feature__key', 'is_enabled'))
        return {
            key
            for key, is_globally_enabled in Feature.objects.values_list('key', 'is_enabled')
            if override_by_key.get(key, is_globally_enabled)
        }

    def has_feature(self, key):
        return key in self.get_enabled_feature_keys()


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

    def get_events(self, exclude_upcoming=False):
        qs = self.user.event_results.filter(
            event__playgroups=self.playgroup
        ).order_by('-event__start_date')
        if exclude_upcoming:
            qs = exclude_upcoming_event_results(qs)
        return qs

    def get_events_won(self):
        return self.get_events().filter(finishing_position=1)

    def get_num_match_wins(self):
        return self.get_events().aggregate(Sum('num_wins'))['num_wins__sum'] or 0


class PlaygroupJoinRequest(models.Model):
    class RequestStatuses(models.IntegerChoices):
        SUBMITTED = (0, _('Submitted'))
        ACCEPTED = (1, _('Accepted'))
        DECLINED = (2, _('Declined'))
        CANCELLED = (3, _('Cancelled'))

    playgroup = models.ForeignKey(
        Playgroup, on_delete=models.CASCADE, related_name='join_requests')
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    note = models.TextField(default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    status = models.IntegerField(
        choices=RequestStatuses.choices, default=RequestStatuses.SUBMITTED)

    class Meta:
        ordering = ['-created_on']

    def __str__(self):
        return f'{self.user.username} - {self.playgroup.name}'


class Venue(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    address = models.TextField(
        help_text=_('Enter the full address as it would appear on mail')
    )
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, default=None, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, default=None, null=True, blank=True
    )
    formatted_address = models.CharField(
        max_length=500, default=None, null=True, blank=True
    )
    city = models.CharField(
        max_length=100, default=None, null=True, blank=True)
    state_province = models.CharField(
        max_length=100, default=None, null=True, blank=True
    )
    country = models.CharField(
        max_length=100, default=None, null=True, blank=True
    )
    country_code = models.CharField(
        max_length=2, default=None, null=True, blank=True
    )
    postal_code = models.CharField(
        max_length=20, default=None, null=True, blank=True
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        default=None, null=True, blank=True, related_name='created_venues'
    )

    objects = VenueQuerySet.as_manager()

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    def has_coordinates(self):
        return self.latitude is not None and self.longitude is not None

    def geocode(self, save=True):
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut, GeocoderServiceError

        geolocator = Nominatim(user_agent="keychain-sloppylabwork")
        try:
            location = geolocator.geocode(
                self.address, addressdetails=True, timeout=5)
            if location:
                self.latitude = location.latitude
                self.longitude = location.longitude
                self.formatted_address = location.address

                address_data = location.raw.get('address', {})
                self.city = (
                    address_data.get('city') or
                    address_data.get('town') or
                    address_data.get('village') or
                    address_data.get('municipality')
                )
                self.state_province = (
                    address_data.get('state') or
                    address_data.get('province') or
                    address_data.get('region') or
                    address_data.get('prefecture')
                )
                self.country = address_data.get('country')
                self.country_code = address_data.get(
                    'country_code', '').upper()
                self.postal_code = address_data.get('postcode')

                if save:
                    self.save()
                return True
        except (GeocoderTimedOut, GeocoderServiceError):
            pass
        return False


class PlaygroupVenue(models.Model):
    playgroup = models.ForeignKey(
        Playgroup, on_delete=models.CASCADE, related_name='playgroup_venues'
    )
    venue = models.ForeignKey(
        Venue, on_delete=models.CASCADE, related_name='playgroup_venues'
    )
    added_on = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        default=None, null=True, blank=True
    )

    class Meta:
        unique_together = ('playgroup', 'venue')
        ordering = ('venue__name',)

    def __str__(self):
        return f'{self.playgroup.name} - {self.venue.name}'


class EventFormat(models.Model):
    name = models.CharField(max_length=200, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ('sort_order', 'name',)

    def __str__(self):
        return self.name


class EventTag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.CharField(
        max_length=200, default=None, null=True, blank=True)
    is_eo_assignable = models.BooleanField(default=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class Event(models.Model):
    EVENT_TYPE_CHOICES = (
        (False, _('Tournament')),
        (True, _('Open Play')),
    )

    name = models.CharField(max_length=200)
    description = models.TextField(default=None, null=True, blank=True)
    start_date = models.DateField(default=date.today)
    player_count = models.SmallIntegerField(default=0)
    format = models.ForeignKey(EventFormat, on_delete=models.SET_NULL,
                               related_name='events', default=None, null=True, blank=True)
    is_excluded_from_xp = models.BooleanField(default=False)
    is_casual = models.BooleanField(default=False, choices=EVENT_TYPE_CHOICES)
    is_excluded_from_global_rankings = models.BooleanField(default=False)
    is_digital = models.BooleanField(default=False)
    is_accepting_registrations = models.BooleanField(default=False)
    tags = models.ManyToManyField(EventTag, related_name='events', blank=True)

    class Meta:
        ordering = ('-start_date',)

    @property
    def is_registration_open(self):
        if not self.is_accepting_registrations:
            return False
        if self.start_date < date.today() - timedelta(days=1):
            return False
        if self.results.filter(finishing_position__isnull=False).exists():
            return False
        return True

    @property
    def is_upcoming(self):
        if self.start_date < date.today() - timedelta(days=1):
            return False
        if self.results.filter(finishing_position__isnull=False).exists():
            return False
        return True

    @property
    def is_eligible_for_tourney_creation(self):
        if self.tournaments.exists():
            return False
        registrations = self.results.all()
        if not registrations.exists():
            return False
        return not registrations.filter(
            Q(finishing_position__isnull=False) |
            Q(num_wins__isnull=False) |
            Q(num_losses__isnull=False)
        ).exists()

    def has_ties(self):
        return self.results.filter(num_ties__isnull=False, num_ties__gt=0).exists()

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
    xp_for_casual_attendance = 50
    xp_for_attendance = 25
    xp_for_win = 10
    xp_for_loss = 5

    xp_for_digital_casual_attendance = 0
    xp_for_digital_attendance = 12
    xp_for_digital_win = 5
    xp_for_digital_loss = 2

    max_deck_lookup_attempts = 3

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
    num_ties = models.PositiveSmallIntegerField(
        default=None, null=True, blank=True)
    uploaded_deck_link = models.URLField(
        default=None, null=True, blank=True)
    uploaded_deck_lookup_attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('finishing_position', '-num_wins', 'num_losses', 'num_ties')
        unique_together = ('event', 'user',)

    @property
    def formatted_record(self):
        if self.num_wins is None and self.num_losses is None and self.num_ties is None:
            return "–"
        w = self.num_wins if self.num_wins is not None else 0
        l = self.num_losses if self.num_losses is not None else 0
        if self.num_ties:
            return f"{w}–{l}–{self.num_ties}"
        return f"{w}–{l}"

    @property
    def formatted_record_with_ties(self):
        if self.num_wins is None and self.num_losses is None and self.num_ties is None:
            return "–"
        w = self.num_wins if self.num_wins is not None else 0
        l = self.num_losses if self.num_losses is not None else 0
        t = self.num_ties if self.num_ties is not None else 0
        return f"{w}–{l}–{t}"

    def __str__(self):
        return f'{self.event.name} - {self.user} - ({self.finishing_position})'

    def get_xp(self):
        if self.event.is_digital:
            return self._get_xp_digital()
        return self._get_xp()

    def _get_xp(self):
        if self.event.is_excluded_from_xp or not self.event.player_count > 1:
            return 0
        if self.event.is_casual:
            return self.xp_for_casual_attendance
        xp = self.xp_for_attendance
        if self.num_wins:
            xp += self.num_wins * self.xp_for_win
        if self.num_losses:
            xp += self.num_losses * self.xp_for_loss
        if self.num_ties:
            xp += self.num_ties * self.xp_for_loss
        return min(xp, 100)

    def _get_xp_digital(self):
        if self.event.is_excluded_from_xp or not self.event.player_count > 1:
            return 0
        if self.event.is_casual:
            return self.xp_for_digital_casual_attendance
        xp = self.xp_for_digital_attendance
        if self.num_wins:
            xp += self.num_wins * self.xp_for_digital_win
        if self.num_losses:
            xp += self.num_losses * self.xp_for_digital_loss
        if self.num_ties:
            xp += self.num_ties * self.xp_for_digital_loss
        return min(xp, 100)

    def add_deck_by_uploaded_link(self):
        if not self.uploaded_deck_link or self.uploaded_deck_lookup_attempts >= self.max_deck_lookup_attempts:
            raise ValueError(
                _('Deck link is required and lookup attempts exceeded.'))

        try:
            with transaction.atomic():
                mv_id = Deck.get_id_from_master_vault_url(
                    self.uploaded_deck_link)
                deck, _created = Deck.objects.get_or_create(id=mv_id)
                deck.hydrate_from_master_vault(save=True)
                EventResultDeck.objects.create(
                    event_result=self,
                    deck=deck
                )
                self.uploaded_deck_link = None
                self.uploaded_deck_lookup_attempts = 0
                self.save()
        except Exception as e:
            self.uploaded_deck_lookup_attempts += 1
            self.save()
            raise e


class EventResultDeck(models.Model):
    event_result = models.ForeignKey(
        EventResult, on_delete=models.CASCADE, related_name='event_result_decks')
    deck = models.ForeignKey(
        'decks.Deck', on_delete=models.CASCADE, related_name='event_results')
    was_played = models.BooleanField(default=True)
    added_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event_result', 'deck',)
        ordering = ('event_result__event__start_date', 'deck__name',)

    def __str__(self):
        return f'{self.event_result.event.name} - {self.deck}'


class RankingPointsMapVersion(models.Model):
    name = models.CharField(max_length=100)
    effective_on = models.DateField(unique=True)

    def __str__(self):
        return self.name


class RankingPointsMap(models.Model):
    max_players = models.PositiveSmallIntegerField()
    finishing_position = models.PositiveSmallIntegerField()
    points = models.PositiveIntegerField()
    version = models.ForeignKey(
        RankingPointsMapVersion, on_delete=models.CASCADE, related_name='points_map_entries', default=None, null=True, blank=True)

    @staticmethod
    def list_points_for_fp_ranges(event_size, version=None):
        filters = {'max_players': event_size}
        if version:
            filters['version'] = version

        ranking_data = RankingPointsMap.objects.filter(**filters).order_by(
            "finishing_position").values("finishing_position", "points")
        result = []
        for index, entry in enumerate(ranking_data):
            start_position = entry["finishing_position"]
            points = entry["points"]
            next_position = ranking_data[index + 1]["finishing_position"] - \
                1 if index + 1 < len(ranking_data) else event_size
            position_range = f"{start_position}-{next_position}" if start_position != next_position else f"{start_position}"
            result.append({
                "position_range": position_range,
                "points": points
            })
        return result

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


class LeaderboardSeasonPeriodManager(models.Manager):
    def update_all_lock_statuses(self):
        unlocked = self.filter(is_locked=False).exclude(
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.ALL_TIME
        )
        locked_count = 0
        for period in unlocked:
            if period.update_lock_status():
                locked_count += 1
        return locked_count


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
    is_locked = models.BooleanField(default=False)

    objects = LeaderboardSeasonPeriodManager()

    class Meta:
        ordering = ('-start_date',)
        UniqueConstraint(fields=['start_date', 'frequency'],
                         name='unique_leaderboard_period')

    def __str__(self):
        return f'{self.name}'

    def get_end_date(self):
        next_period = LeaderboardSeasonPeriod.objects.filter(
            frequency=self.frequency,
            start_date__gt=self.start_date
        ).order_by("start_date").first()
        return next_period.start_date if next_period else date.today() + timedelta(days=1)

    def should_be_locked(self) -> bool:
        if self.frequency == self.FrequencyOptions.ALL_TIME:
            return False

        end_date = self.get_end_date()
        return date.today() >= end_date + timedelta(days=7)

    def update_lock_status(self):
        should_lock = self.should_be_locked()
        if should_lock and not self.is_locked:
            self.is_locked = True
            self.save(update_fields=['is_locked'])
            return True
        return False


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


class PlaygroupLeaderboard(models.Model):
    """Allows for playgroup-specific leaderboard settings

    By default, leaderboards are available to all playgroups. This model allows
    for advanced configuration.

    All properties should be considered optional with default "empty" states.
    """
    playgroup = models.ForeignKey(
        Playgroup, on_delete=models.CASCADE, related_name='leaderboard_settings')
    leaderboard = models.ForeignKey(
        Leaderboard, on_delete=models.CASCADE, related_name='leaderboard_settings')

    is_leaderboard_hidden = models.BooleanField(default=False)

    class Meta:
        unique_together = ('playgroup', 'leaderboard',)


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
    class ThemeOptions(models.IntegerChoices):
        KEYCHAIN_DARK = (0, _('KeyChain Dark'))
        KEYCHAIN_LIGHT = (1, _('KeyChain Light'))

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='pmc_profile')
    avatar = models.ForeignKey(
        'Avatar', on_delete=models.SET_NULL, default=None, null=True, blank=True)
    background = models.ForeignKey(
        'Background', on_delete=models.SET_NULL, default=None, null=True, blank=True)
    pronouns = models.CharField(
        max_length=100, default=None, null=True, blank=True)
    theme = models.IntegerField(
        choices=ThemeOptions.choices, default=ThemeOptions.KEYCHAIN_DARK)
    tagline = models.CharField(
        max_length=100, default=None, null=True, blank=True)
    mv_id = models.CharField(max_length=36, unique=True,
                             default=None, null=True, blank=True)
    mv_username = models.CharField(
        max_length=100, default=None, null=True, blank=True)
    mv_qrcode_message = models.CharField(
        max_length=200, default=None, null=True, blank=True)
    show_stats_on_profile = models.BooleanField(
        default=False,
        help_text=_('Including your level'),
        verbose_name=_('Stats')
    )
    show_awards_on_profile = models.BooleanField(
        default=False,
        verbose_name=_('Awards')
    )
    show_playgroups_on_profile = models.BooleanField(
        default=False,
        verbose_name=_('Playgroups')
    )

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

    def get_events(self, exclude_upcoming=False):
        qs = self.user.event_results.order_by('-event__start_date')
        if exclude_upcoming:
            qs = exclude_upcoming_event_results(qs)
        return qs

    def get_events_won(self):
        return self.get_events().filter(finishing_position=1)

    def get_num_match_wins(self):
        return self.get_events().aggregate(Sum('num_wins'))['num_wins__sum'] or 0

    def get_total_xp(self):
        event_results = EventResult.objects.filter(
            user=self.user,
            event__is_excluded_from_xp=False
        )
        total_xp = 0
        for result in event_results:
            total_xp += result.get_xp()

        return total_xp

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
        if not event_results:
            return

        if event_results and event_results[0].event.is_casual:
            RankingPoints.objects.filter(
                result__event=event_results[0].event).delete()
            return

        rp_map_version = RankingPointsMapVersion.objects.filter(
            effective_on__lte=event_results[0].event.start_date
        ).order_by('-effective_on').first()

        rp_map_entries = RankingPointsMap.objects.filter(
            version=rp_map_version,
            max_players=RankingPointsMap.objects
            .filter(
                max_players__gte=player_count,
                version=rp_map_version,
            )
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
        if event.is_casual:
            RankingPoints.objects.filter(result__event=event).delete()
            return

        results = event.results.all()
        RankingPoints.objects.filter(result__event=event).delete()
        return RankingPointsService.assign_points_for_results(
            results, event.player_count or len(results)
        )

    @staticmethod
    def assign_points_for_leaderboard(leaderboard, ranking_period, order_by='total_points', top_n_per_month=5):
        """
        Updates PlayerRank records based on the top N highest-scoring RankingPoints
        within a given ranking period. Computes both global and playgroup rankings.

        Args:
            leaderboard (Leaderboard): The leaderboard for which ranks are being calculated.
            ranking_period (LeaderboardSeasonPeriod): The period defining the date range.
            order_by (str): Field to sort rankings by (default: 'total_points').
            top_n_per_month (int): The number of highest-scoring results per calendar month to consider.
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

        from django.db.models.functions import TruncMonth, RowNumber

        ranked_points = ranking_points_qs.annotate(
            month=TruncMonth('result__event__start_date'),
            point_rank=Window(
                expression=RowNumber(),
                partition_by=[F("result__user"), F("month")],
                order_by=["-points"]
            )
        ).filter(point_rank__lte=top_n_per_month)

        def compute_rankings(playgroup=None):
            filters = {}
            if playgroup:
                filters["result__event__playgroups"] = playgroup
                base_qs = ranking_points_qs
            else:
                filters["result__event__is_excluded_from_global_rankings"] = False
                base_qs = ranked_points

            raw_results = base_qs.filter(**filters).values_list(
                "result__user", "points"
            )

            monthly_data = {}
            for user_id, points in raw_results:
                if user_id not in monthly_data:
                    monthly_data[user_id] = {
                        "total_points": 0, "num_results": 0}
                monthly_data[user_id]["total_points"] += points
                monthly_data[user_id]["num_results"] += 1

            top_n_user_points = [
                {
                    "result__user": user_id,
                    "total_points": data["total_points"],
                    "num_results": data["num_results"]
                }
                for user_id, data in monthly_data.items()
            ]

            user_data = {entry["result__user"]: {
                "total_points": entry["total_points"],
                "num_results": entry["num_results"],
                "avg_points": entry["total_points"] / entry["num_results"] if entry["num_results"] > 0 else 0
            }
                for entry in top_n_user_points
            }

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
            rank_with_ties = 1
            prev_value = None
            for ix, pr in enumerate(player_ranks, start=1):
                current_value = getattr(pr, order_by)
                if current_value != prev_value:
                    rank_with_ties = ix
                prev_value = current_value
                pr.rank = rank_with_ties

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


class AvatarCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=1)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ('sort_order', 'name',)

    def __str__(self):
        return self.name


class BackgroundCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=1)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ('sort_order', 'name',)

    def __str__(self):
        return self.name


class Avatar(models.Model):
    pmc_id = models.CharField(max_length=10, unique=True)
    src = models.URLField()
    category = models.ForeignKey(
        AvatarCategory, on_delete=models.CASCADE, related_name='avatars', default=None, null=True)
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
    category = models.ForeignKey(
        BackgroundCategory, on_delete=models.CASCADE, related_name='backgrounds', default=None, null=True)
    name = models.CharField(max_length=100)
    required_level = models.PositiveIntegerField(default=0)
    artist_credit = models.CharField(
        max_length=100, default=None, null=True, blank=True)

    @property
    def src_100(self):
        return self.src.replace('/upload/', '/upload/c_thumb,w_100,h_100,f_auto,q_auto/')

    class Meta:
        ordering = ('required_level', 'pmc_id')

    def __str__(self):
        return self.name


class AwardBase(models.Model):
    class RewardCategoryOptions(models.IntegerChoices):
        PARTICIPATION = (0, _('Participation'))
        SKILL = (1, _('Skill'))
        TASK = (2, _('Task'))

    class ModeOptions(models.IntegerChoices):
        IN_PERSON = (0, _('In-Person'))
        ONLINE = (1, _('Online'))
        ANY = (2, _('Any'))

    class CriteriaTypeOptions(models.IntegerChoices):
        event_matches = (0, _('Event Matches'))
        sealed_event_matches = (1, _('Sealed Event Matches'))
        archon_event_matches = (2, _('Archon Event Matches'))
        alliance_event_matches = (3, _('Alliance Event Matches'))
        adaptive_event_matches = (4, _('Adaptive Event Matches'))
        tournament_match_wins = (5, _('Tournament Match Wins'))
        sealed_tournament_match_wins = (6, _('Sealed Tournament Match Wins'))
        archon_tournament_match_wins = (7, _('Archon Tournament Match Wins'))
        alliance_tournament_match_wins = (
            8, _('Alliance Tournament Match Wins'))
        adaptive_tournament_match_wins = (
            9, _('Adaptive Tournament Match Wins'))
        events = (10, _('Events'))
        win_a_tournament_3_to_5 = (
            11, _('Win a Tournament (3-5 Players, Excluding Premier)'))
        win_a_tournament_6_plus = (
            12, _('Win a Tournament (6+ Players, Excluding Premier)'))
        second_place_a_tournament_6_plus = (
            13, _('Second Place in a Tournament (6+ Players)'))
        third_place_a_tournament_6_plus = (
            14, _('Third Place in a Tournament (6-10 Players)'))
        top_four_a_tournament_11_plus = (
            15, _('Top Four in a Tournament (11+ Players)'))
        top_eight_a_tournament_11_plus = (
            16, _('Top Eight in a Tournament (11+ Players)'))
        store_champion = (17, _('Store Champion'))
        vault_warrior = (18, _('Vault Warrior'))
        world_champion = (19, _('World Champion'))
        level = (20, _('Level'))
        events_at_group_in_calendar_month = (
            21, _('Events at Group in Calendar Month'))
        tournament_match_wins_with_house = (
            22, _('Tournament Match Wins with House'))
        sets_with_ten_tournament_match_wins = (
            23, _('Sets with Ten Tournament Match Wins'))
        playgroup_leaderboard_season_first_place = (
            24, _('Playgroup Leaderboard Season - First Place'))
        playgroup_leaderboard_season_second_place = (
            25, _('Playgroup Leaderboard Season - Second Place'))
        playgroup_leaderboard_season_third_place = (
            26, _('Playgroup Leaderboard Season - Third Place'))
        playgroup_leaderboard_season_top_five = (
            27, _('Playgroup Leaderboard Season - Top Five'))
        playgroup_leaderboard_season_top_ten = (
            28, _('Playgroup Leaderboard Season - Top Ten'))
        global_leaderboard_season_first_place = (
            29, _('Global Leaderboard Season - First Place'))
        global_leaderboard_season_top_ten = (
            30, _('Global Leaderboard Season - Top Ten'))
        global_leaderboard_season_top_fifty = (
            31, _('Global Leaderboard Season - Top Fifty'))
        global_leaderboard_season_top_one_hundred = (
            32, _('Global Leaderboard Season - Top One Hundred'))
        global_leaderboard_monthly_first_place = (
            33, _('Global Leaderboard Monthly - First Place'))
        global_leaderboard_monthly_top_ten = (
            34, _('Global Leaderboard Monthly - Top Ten'))
        global_leaderboard_monthly_top_twenty_five = (
            35, _('Global Leaderboard Monthly - Top Twenty Five'))
        global_leaderboard_monthly_top_fifty = (
            36, _('Global Leaderboard Monthly - Top Fifty'))
        participate_in_premier_tournament = (
            37, _('Participate in Premier Tournament'))
        kfc_open_champion = (38, _('KFC Open Champion'))
        national_champion_belgium = (39, _('National Champion: Belgium'))
        national_champion_brazil = (40, _('National Champion: Brazil'))
        national_champion_canada = (41, _('National Champion: Canada'))
        national_champion_china = (42, _('National Champion: China'))
        national_champion_denmark = (43, _('National Champion: Denmark'))
        national_champion_italy = (44, _('National Champion: Italy'))
        national_champion_netherlands = (
            45, _('National Champion: Netherlands'))
        national_champion_poland = (46, _('National Champion: Poland'))
        national_champion_portugal = (47, _('National Champion: Portugal'))
        national_champion_south_korea = (
            48, _('National Champion: South Korea'))
        national_champion_sweden = (49, _('National Champion: Sweden'))
        national_champion_taiwan = (50, _('National Champion: Taiwan'))
        national_champion_united_kingdom = (
            51, _('National Champion: United Kingdom'))
        national_champion_united_states = (
            52, _('National Champion: United States'))
        national_champion_france = (53, _('National Champion: France'))
        national_champion_chile = (54, _('National Champion: Chile'))
        national_champion_germany = (55, _('National Champion: Germany'))
        national_champion_greece = (56, _('National Champion: Greece'))

        manually_awarded = (999, _('Manually Awarded'))

    pmc_id = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(default=None, null=True, blank=True)
    reward_category = models.IntegerField(
        choices=RewardCategoryOptions.choices, default=RewardCategoryOptions.PARTICIPATION)
    is_hidden = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=1)
    house = models.ForeignKey(
        'decks.House', on_delete=models.SET_NULL, default=None, null=True, blank=True)
    mode = models.IntegerField(
        choices=ModeOptions.choices, default=ModeOptions.IN_PERSON)

    class Meta:
        abstract = True
        ordering = ('sort_order', 'name',)

    def __str__(self):
        return self.name


class AwardCredit(models.Model):
    criteria = models.IntegerField(
        choices=AwardBase.CriteriaTypeOptions.choices)
    amount = models.PositiveIntegerField(default=1)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='award_credits')
    added_on = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(default=None, null=True, blank=True)


class Achievement(AwardBase):
    """ Achievements are tiered awards.

    They will have a single type of criteria with levels of achievement.
    Individual tiers will express the criteria levels to be achieved.
    """
    criteria = models.IntegerField(
        choices=AwardBase.CriteriaTypeOptions.choices)

    @classmethod
    def with_highest_user_achievements_tier(cls, user):
        user_achievement_tiers = UserAchievementTier.objects.filter(
            user=user,
            achievement_tier__achievement=OuterRef('pk')
        )
        return cls.objects.annotate(
            user_achievement_tier=Subquery(
                user_achievement_tiers.order_by('-achievement_tier__tier').values('achievement_tier__tier')[:1]),
            user_achievement_tier_src=Subquery(
                user_achievement_tiers.order_by('-achievement_tier__tier').values('achievement_tier__src')[:1]),
            lowest_tier_src=Subquery(
                AchievementTier.objects.filter(
                    achievement=OuterRef('pk')
                ).order_by('tier').values('src')[:1]
            )
        )

    def get_bronze_tier_src(self):
        return self.tiers.filter(tier=AchievementTier.TierOptions.BRONZE).first().src


class AchievementTier(models.Model):
    class TierOptions(models.IntegerChoices):
        BRONZE = (0, _('Bronze'))
        SILVER = (1, _('Silver'))
        GOLD = (2, _('Gold'))
        ASCENSION = (3, _('Ascension'))
    achievement = models.ForeignKey(
        Achievement, on_delete=models.CASCADE, related_name='tiers')
    tier = models.IntegerField(choices=TierOptions.choices)
    criteria_value = models.PositiveIntegerField(default=1)
    src = models.URLField(default=None, null=True, blank=True)

    class Meta:
        ordering = ('tier',)
        constraints = [
            UniqueConstraint(fields=['achievement', 'tier'],
                             name='unique_achievement_tier'),
        ]

    def __str__(self):
        return f'{self.achievement.name} - {self.tier}'


class Badge(AwardBase):
    """One-time awards, typically granted by an EO
    """
    src = models.URLField(default=None, null=True, blank=True)
    is_eo_assignable = models.BooleanField(default=True)

    @classmethod
    def with_user_badges(cls, user):
        user_badges = UserBadge.objects.filter(
            user=user,
            badge=OuterRef('pk')
        )
        return cls.objects.annotate(
            user_badge_id=Subquery(user_badges.values('id')[:1])
        )


class Trophy(AwardBase):
    """Trohpies are baed on stats and may be earned any number of times.
    """
    criteria = models.IntegerField(
        choices=AwardBase.CriteriaTypeOptions.choices)
    criteria_value = models.PositiveIntegerField(default=1)
    src = models.URLField(default=None, null=True, blank=True)

    @classmethod
    def with_user_trophies(cls, user):
        user_trophies = UserTrophy.objects.filter(
            user=user,
            trophy=OuterRef('pk')
        )
        return cls.objects.annotate(
            user_trophy_amount=Subquery(user_trophies.values('amount')[:1])
        )

    class Meta:
        verbose_name_plural = _('Trophies')
        ordering = ('sort_order', 'name',)


class UserAchievementTier(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='achievement_tiers')
    achievement_tier = models.ForeignKey(
        AchievementTier, on_delete=models.CASCADE, related_name='user_achievement_tiers')
    date_awarded = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['user', 'achievement_tier'],
                             name='unique_user_achievement_tier'),
        ]

    def __str__(self):
        return f'{self.user.username} - {self.achievement_tier.achievement.name} - {self.achievement_tier.tier}'


class UserBadge(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='badges')
    badge = models.ForeignKey(
        Badge, on_delete=models.CASCADE, related_name='user_badges')
    date_awarded = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['user', 'badge'],
                             name='unique_user_badge'),
        ]

    def __str__(self):
        return f'{self.user.username} - {self.badge.name}'


class UserTrophy(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='trophies')
    trophy = models.ForeignKey(
        Trophy, on_delete=models.CASCADE, related_name='user_trophies')
    date_awarded = models.DateTimeField(auto_now_add=True)
    amount = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['user', 'trophy'],
                             name='unique_user_trophy'),
        ]
        verbose_name_plural = _('User trophies')

    def __str__(self):
        return f'{self.user.username} - {self.trophy.name}'


class PinnedAward(models.Model):
    class AwardTypeOptions(models.IntegerChoices):
        BADGE = (0, _('Badge'))
        ACHIEVEMENT = (1, _('Achievement'))
        TROPHY = (2, _('Trophy'))

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='pinned_awards')
    award_type = models.IntegerField(choices=AwardTypeOptions.choices)
    award_id = models.PositiveIntegerField()
    position = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)])

    class Meta:
        ordering = ('position',)
        constraints = [
            UniqueConstraint(
                fields=['user', 'position'],
                name='unique_user_pin_position'),
            UniqueConstraint(
                fields=['user', 'award_type', 'award_id'],
                name='unique_user_pinned_award'),
        ]

    def __str__(self):
        return f'{self.user.username} - Pin {self.position}: {self.get_award_type_display()} #{self.award_id}'

    @staticmethod
    def get_pinned_awards_for_display(user):
        pins = PinnedAward.objects.filter(user=user).order_by('position')
        if not pins:
            return []

        badge_ids = [p.award_id for p in pins if p.award_type == PinnedAward.AwardTypeOptions.BADGE]
        achievement_ids = [p.award_id for p in pins if p.award_type == PinnedAward.AwardTypeOptions.ACHIEVEMENT]
        trophy_ids = [p.award_id for p in pins if p.award_type == PinnedAward.AwardTypeOptions.TROPHY]

        badges = {b.pk: b for b in Badge.objects.filter(pk__in=badge_ids)} if badge_ids else {}
        trophies = {t.pk: t for t in Trophy.objects.filter(pk__in=trophy_ids)} if trophy_ids else {}

        achievement_tiers = {}
        if achievement_ids:
            user_tiers = UserAchievementTier.objects.filter(
                user=user,
                achievement_tier__achievement_id__in=achievement_ids
            ).select_related('achievement_tier', 'achievement_tier__achievement').order_by(
                'achievement_tier__achievement_id', '-achievement_tier__tier'
            )
            for ut in user_tiers:
                aid = ut.achievement_tier.achievement_id
                if aid not in achievement_tiers:
                    achievement_tiers[aid] = ut.achievement_tier

        results = []
        for pin in pins:
            src = None
            name = None
            if pin.award_type == PinnedAward.AwardTypeOptions.BADGE:
                badge = badges.get(pin.award_id)
                if badge:
                    src, name = badge.src, badge.name
            elif pin.award_type == PinnedAward.AwardTypeOptions.ACHIEVEMENT:
                tier = achievement_tiers.get(pin.award_id)
                if tier:
                    src = tier.src
                    name = tier.achievement.name
            elif pin.award_type == PinnedAward.AwardTypeOptions.TROPHY:
                trophy = trophies.get(pin.award_id)
                if trophy:
                    src, name = trophy.src, trophy.name
            if src:
                url_names = {
                    PinnedAward.AwardTypeOptions.BADGE: 'pmc-my-badge-detail',
                    PinnedAward.AwardTypeOptions.ACHIEVEMENT: 'pmc-my-achievement-detail',
                    PinnedAward.AwardTypeOptions.TROPHY: 'pmc-my-trophy-detail',
                }
                from django.urls import reverse
                results.append({
                    'pk': pin.pk,
                    'position': pin.position,
                    'src': src,
                    'name': name,
                    'award_type': pin.award_type,
                    'award_id': pin.award_id,
                    'detail_url': reverse(url_names[pin.award_type], args=[pin.award_id]),
                })

        return results

    @staticmethod
    def next_position(user):
        last = PinnedAward.objects.filter(user=user).order_by('-position').first()
        if not last:
            return 1
        return last.position + 1 if last.position < 5 else None

    @staticmethod
    def recompact_positions(user):
        pins = PinnedAward.objects.filter(user=user).order_by('position')
        for i, pin in enumerate(pins, start=1):
            if pin.position != i:
                pin.position = i
                pin.save(update_fields=['position'])


class AwardAssignmentService():
    """
    Helper for assigning trophies to users based on their stats and trophy criteria.
    """

    @staticmethod
    def refresh_trophy(pmc_id):
        trophy = Trophy.objects.filter(pmc_id=pmc_id).first()
        if not trophy:
            return
        if trophy.criteria == AwardBase.CriteriaTypeOptions.manually_awarded:
            return

        UserTrophy.objects.filter(trophy=trophy).delete()
        users = User.objects.all()
        for user in users:
            value = AwardAssignmentService.get_user_criteria_value(
                user, trophy)
            amount = value // trophy.criteria_value if trophy.criteria_value else 0
            if amount > 0:
                UserTrophy.objects.update_or_create(
                    user=user,
                    trophy=trophy,
                    defaults={'amount': amount}
                )

    @staticmethod
    def refresh_achievement(pmc_id):
        achievement = Achievement.objects.filter(pmc_id=pmc_id).first()
        if not achievement:
            return

        UserAchievementTier.objects.filter(
            achievement_tier__achievement=achievement
        ).delete()
        tiers = achievement.tiers.all()
        users = User.objects.all()
        for user in users:
            user_value = AwardAssignmentService.get_user_criteria_value(
                user, achievement)
            for tier in tiers:
                if user_value >= tier.criteria_value:
                    UserAchievementTier.objects.update_or_create(
                        user=user,
                        achievement_tier=tier
                    )

    @staticmethod
    def refresh_all_user_trophies():
        """
        Refreshes all user trophies by re-evaluating the criteria for each trophy.
        """
        UserTrophy.objects.exclude(
            trophy__criteria=AwardBase.CriteriaTypeOptions.manually_awarded
        ).delete()
        trophies = Trophy.objects.exclude(
            criteria=AwardBase.CriteriaTypeOptions.manually_awarded
        )
        users = User.objects.all()
        for user in users:
            for trophy in trophies:
                value = AwardAssignmentService.get_user_criteria_value(
                    user, trophy)
                amount = value // trophy.criteria_value if trophy.criteria_value else 0
                if amount > 0:
                    UserTrophy.objects.update_or_create(
                        user=user,
                        trophy=trophy,
                        defaults={'amount': amount}
                    )

    @staticmethod
    def refresh_user_achievements(
        pmc_id_min=None,
        pmc_id_max=None
    ):
        qs = UserAchievementTier.objects.all()
        if pmc_id_min is not None:
            qs = qs.filter(
                achievement_tier__achievement__pmc_id__gte=pmc_id_min)
        if pmc_id_max is not None:
            qs = qs.filter(
                achievement_tier__achievement__pmc_id__lte=pmc_id_max)
        qs.delete()
        users = User.objects.all()
        achievements = Achievement.objects.all()
        if pmc_id_min is not None:
            achievements = achievements.filter(pmc_id__gte=pmc_id_min)
        if pmc_id_max is not None:
            achievements = achievements.filter(pmc_id__lte=pmc_id_max)
        for achievement in achievements:
            tiers = achievement.tiers.all()
            for user in users:
                user_value = AwardAssignmentService.get_user_criteria_value(
                    user, achievement)
                for tier in tiers:
                    if user_value >= tier.criteria_value:
                        UserAchievementTier.objects.update_or_create(
                            user=user,
                            achievement_tier=tier
                        )

    @staticmethod
    def refresh_user_badges():
        badge = Badge.objects.filter(pmc_id='071').first()
        if badge:
            UserBadge.objects.filter(
                badge=badge,
                user__pmc_profile__mv_username__isnull=True
            ).delete()
            users_with_mv_username = User.objects.filter(
                pmc_profile__mv_username__isnull=False
            )
            for user in users_with_mv_username:
                UserBadge.objects.update_or_create(user=user, badge=badge)

    @staticmethod
    def get_user_criteria_value(user, award):
        criteria_type = award.criteria
        value = 0

        event_result_mode_filter = models.Q()
        event_result_event_mode_filter = models.Q()
        if award.mode == AwardBase.ModeOptions.IN_PERSON:
            event_result_mode_filter = models.Q(event__is_digital=False)
            event_result_event_mode_filter = models.Q(
                event_result__event__is_digital=False)
        elif award.mode == AwardBase.ModeOptions.ONLINE:
            event_result_mode_filter = models.Q(event__is_digital=True)
            event_result_event_mode_filter = models.Q(
                event_result__event__is_digital=True)

        qs = EventResult.objects.filter(
            user=user).filter(event_result_mode_filter)

        if criteria_type == AwardBase.CriteriaTypeOptions.event_matches:
            value = qs.aggregate(
                total=Coalesce(Sum('num_wins'), 0) +
                Coalesce(Sum('num_losses'), 0)
            )['total']
        elif criteria_type == AwardBase.CriteriaTypeOptions.sealed_event_matches:
            value = qs.filter(event__format__name__icontains='Sealed').aggregate(
                total=Coalesce(Sum('num_wins'), 0) +
                Coalesce(Sum('num_losses'), 0)
            )['total']
        elif criteria_type == AwardBase.CriteriaTypeOptions.archon_event_matches:
            value = qs.filter(event__format__name__icontains='Archon').aggregate(
                total=Coalesce(Sum('num_wins'), 0) +
                Coalesce(Sum('num_losses'), 0)
            )['total']
        elif criteria_type == AwardBase.CriteriaTypeOptions.alliance_event_matches:
            value = qs.filter(event__format__name__icontains='Alliance').aggregate(
                total=Coalesce(Sum('num_wins'), 0) +
                Coalesce(Sum('num_losses'), 0)
            )['total']
        elif criteria_type == AwardBase.CriteriaTypeOptions.adaptive_event_matches:
            value = qs.filter(event__format__name__icontains='Adaptive').aggregate(
                total=Coalesce(Sum('num_wins'), 0) +
                Coalesce(Sum('num_losses'), 0)
            )['total']
        elif criteria_type == AwardBase.CriteriaTypeOptions.tournament_match_wins:
            value = qs.filter(event__is_casual=False).aggregate(
                total=Coalesce(Sum('num_wins'), 0)
            )['total']
        elif criteria_type == AwardBase.CriteriaTypeOptions.sealed_tournament_match_wins:
            value = qs.filter(event__is_casual=False, event__format__name__icontains="Sealed").aggregate(
                total=Coalesce(Sum('num_wins'), 0)
            )['total']
        elif criteria_type == AwardBase.CriteriaTypeOptions.archon_tournament_match_wins:
            value = qs.filter(event__is_casual=False, event__format__name__icontains="Archon").aggregate(
                total=Coalesce(Sum('num_wins'), 0)
            )['total']
        elif criteria_type == AwardBase.CriteriaTypeOptions.alliance_tournament_match_wins:
            value = qs.filter(event__is_casual=False, event__format__name__icontains="Alliance").aggregate(
                total=Coalesce(Sum('num_wins'), 0)
            )['total']
        elif criteria_type == AwardBase.CriteriaTypeOptions.adaptive_tournament_match_wins:
            value = qs.filter(event__is_casual=False, event__format__name__icontains="Adaptive").aggregate(
                total=Coalesce(Sum('num_wins'), 0)
            )['total']
        elif criteria_type == AwardBase.CriteriaTypeOptions.win_a_tournament_3_to_5:
            value = qs.filter(
                finishing_position=1,
                event__is_casual=False,
                event__is_excluded_from_global_rankings=False,
                event__player_count__range=(3, 5)
            ).count()
        elif criteria_type == AwardBase.CriteriaTypeOptions.win_a_tournament_6_plus:
            value = qs.filter(
                finishing_position=1,
                event__is_casual=False,
                event__is_excluded_from_global_rankings=False,
                event__player_count__gte=6
            ).count()
        elif criteria_type == AwardBase.CriteriaTypeOptions.events:
            value = qs.count()
        elif criteria_type == AwardBase.CriteriaTypeOptions.second_place_a_tournament_6_plus:
            value = qs.filter(
                finishing_position=2,
                event__is_casual=False,
                event__player_count__gte=6
            ).count()
        elif criteria_type == AwardBase.CriteriaTypeOptions.third_place_a_tournament_6_plus:
            value = qs.filter(
                finishing_position=3,
                event__is_casual=False,
                event__player_count__range=(6, 10)
            ).count()
        elif criteria_type == AwardBase.CriteriaTypeOptions.top_four_a_tournament_11_plus:
            value = qs.filter(
                finishing_position__range=(3, 4),
                event__is_casual=False,
                event__player_count__gte=11
            ).count()
        elif criteria_type == AwardBase.CriteriaTypeOptions.top_eight_a_tournament_11_plus:
            value = qs.filter(
                finishing_position__range=(5, 8),
                event__is_casual=False,
                event__player_count__gte=11
            ).count()
        elif criteria_type == AwardBase.CriteriaTypeOptions.store_champion:
            value = qs.filter(
                event__is_casual=False,
                finishing_position=1,
                event__tags__slug='store-championship'
            ).count()
        elif criteria_type == AwardBase.CriteriaTypeOptions.level:
            current_level = user.pmc_profile.get_level()
            value = current_level.level if current_level else 0
        elif criteria_type == AwardBase.CriteriaTypeOptions.events_at_group_in_calendar_month:
            from django.db.models.functions import TruncMonth
            qualifying_months = (
                EventResult.objects
                .filter(user=user)
                .filter(event_result_mode_filter)
                .filter(event__playgroups__isnull=False)
                .annotate(
                    month=TruncMonth('event__start_date'),
                    playgroup_id=F('event__playgroups')
                )
                .values('month', 'playgroup_id')
                .annotate(event_count=Count('id'))
                .filter(event_count__gte=4)
                .count()
            )
            value = qualifying_months
        elif criteria_type == AwardBase.CriteriaTypeOptions.tournament_match_wins_with_house:
            if not getattr(award, 'house', None):
                return 0
            house = award.house
            event_results = (
                EventResult.objects
                .filter(
                    user=user,
                    event__is_casual=False,
                    event_result_decks__was_played=True
                )
                .filter(event_result_mode_filter)
                .filter(
                    models.Q(event_result_decks__deck__house_1=house) |
                    models.Q(event_result_decks__deck__house_2=house) |
                    models.Q(event_result_decks__deck__house_3=house)
                )
                .values('id', 'num_wins')
                .distinct()
            )
            value = sum(er['num_wins'] or 0 for er in event_results)
        elif criteria_type == AwardBase.CriteriaTypeOptions.sets_with_ten_tournament_match_wins:
            sets_with_10_wins = (
                EventResultDeck.objects
                .filter(
                    event_result__user=user,
                    event_result__event__is_casual=False,
                    was_played=True,
                    deck__set__isnull=False
                )
                .filter(event_result_event_mode_filter)
                .values('deck__set')
                .annotate(total_wins=Sum('event_result__num_wins'))
                .filter(total_wins__gte=10)
                .count()
            )
            value = sets_with_10_wins
        elif criteria_type in [
            AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_first_place,
            AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_second_place,
            AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_third_place,
            AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_top_five,
            AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_top_ten
        ]:
            rank_min_max = (1, 1)
            min_players = 1
            if criteria_type == AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_second_place:
                rank_min_max = (2, 2)
            elif criteria_type == AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_third_place:
                rank_min_max = (3, 3)
            elif criteria_type == AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_top_five:
                rank_min_max = (4, 5)
                min_players = 10
            elif criteria_type == AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_top_ten:
                rank_min_max = (6, 10)
                min_players = 20
            player_count_subquery = PlayerRank.objects.filter(
                playgroup=OuterRef('playgroup'),
                leaderboard=OuterRef('leaderboard'),
                period=OuterRef('period'),
            ).values('playgroup', 'leaderboard', 'period').annotate(
                cnt=Count('id')
            ).values('cnt')
            value = PlayerRank.objects.filter(
                period__is_locked=True,
                user=user,
                rank__gte=rank_min_max[0],
                rank__lte=rank_min_max[1],
                playgroup__isnull=False,
                leaderboard__name='Season'
            ).exclude(
                playgroup__name='Premier Tournaments'
            ).annotate(
                players_in_period=Subquery(player_count_subquery)
            ).filter(
                players_in_period__gte=min_players
            ).count()
        elif criteria_type in [
            AwardBase.CriteriaTypeOptions.global_leaderboard_monthly_first_place,
            AwardBase.CriteriaTypeOptions.global_leaderboard_monthly_top_ten,
            AwardBase.CriteriaTypeOptions.global_leaderboard_monthly_top_twenty_five,
            AwardBase.CriteriaTypeOptions.global_leaderboard_monthly_top_fifty
        ]:
            rank_min_max = (1, 1)
            if criteria_type == AwardBase.CriteriaTypeOptions.global_leaderboard_monthly_top_ten:
                rank_min_max = (2, 10)
            elif criteria_type == AwardBase.CriteriaTypeOptions.global_leaderboard_monthly_top_twenty_five:
                rank_min_max = (11, 25)
            elif criteria_type == AwardBase.CriteriaTypeOptions.global_leaderboard_monthly_top_fifty:
                rank_min_max = (26, 50)
            value = PlayerRank.objects.filter(
                period__is_locked=True,
                user=user,
                rank__gte=rank_min_max[0],
                rank__lte=rank_min_max[1],
                playgroup__isnull=True,
                leaderboard__name='Month'
            ).count()
        elif criteria_type in [
            AwardBase.CriteriaTypeOptions.global_leaderboard_season_first_place,
            AwardBase.CriteriaTypeOptions.global_leaderboard_season_top_ten,
            AwardBase.CriteriaTypeOptions.global_leaderboard_season_top_fifty,
            AwardBase.CriteriaTypeOptions.global_leaderboard_season_top_one_hundred
        ]:
            rank_min_max = (1, 1)
            if criteria_type == AwardBase.CriteriaTypeOptions.global_leaderboard_season_top_ten:
                rank_min_max = (2, 10)
            elif criteria_type == AwardBase.CriteriaTypeOptions.global_leaderboard_season_top_fifty:
                rank_min_max = (11, 50)
            elif criteria_type == AwardBase.CriteriaTypeOptions.global_leaderboard_season_top_one_hundred:
                rank_min_max = (51, 100)
            value = PlayerRank.objects.filter(
                period__is_locked=True,
                user=user,
                rank__gte=rank_min_max[0],
                rank__lte=rank_min_max[1],
                playgroup__isnull=True,
                leaderboard__name='Season'
            ).count()
        elif criteria_type == AwardBase.CriteriaTypeOptions.participate_in_premier_tournament:
            value = qs.filter(
                event__is_casual=False,
                event__playgroup_events__playgroup__name='Premier Tournaments',
            ).count()
        elif criteria_type in [
            AwardBase.CriteriaTypeOptions.kfc_open_champion,
            AwardBase.CriteriaTypeOptions.vault_warrior,
            AwardBase.CriteriaTypeOptions.world_champion,
            AwardBase.CriteriaTypeOptions.national_champion_belgium,
            AwardBase.CriteriaTypeOptions.national_champion_brazil,
            AwardBase.CriteriaTypeOptions.national_champion_canada,
            AwardBase.CriteriaTypeOptions.national_champion_china,
            AwardBase.CriteriaTypeOptions.national_champion_denmark,
            AwardBase.CriteriaTypeOptions.national_champion_italy,
            AwardBase.CriteriaTypeOptions.national_champion_netherlands,
            AwardBase.CriteriaTypeOptions.national_champion_poland,
            AwardBase.CriteriaTypeOptions.national_champion_portugal,
            AwardBase.CriteriaTypeOptions.national_champion_south_korea,
            AwardBase.CriteriaTypeOptions.national_champion_sweden,
            AwardBase.CriteriaTypeOptions.national_champion_taiwan,
            AwardBase.CriteriaTypeOptions.national_champion_united_kingdom,
            AwardBase.CriteriaTypeOptions.national_champion_united_states,
            AwardBase.CriteriaTypeOptions.national_champion_france,
            AwardBase.CriteriaTypeOptions.national_champion_chile,
            AwardBase.CriteriaTypeOptions.national_champion_germany,
            AwardBase.CriteriaTypeOptions.national_champion_greece

        ]:
            tag_slug = {
                AwardBase.CriteriaTypeOptions.kfc_open_champion: 'kfc-open',
                AwardBase.CriteriaTypeOptions.vault_warrior: 'vault-tour',
                AwardBase.CriteriaTypeOptions.world_champion: 'world-championship',
                AwardBase.CriteriaTypeOptions.national_champion_belgium: 'national-championship-belgium',
                AwardBase.CriteriaTypeOptions.national_champion_brazil: 'national-championship-brazil',
                AwardBase.CriteriaTypeOptions.national_champion_canada: 'national-championship-canada',
                AwardBase.CriteriaTypeOptions.national_champion_china: 'national-championship-china',
                AwardBase.CriteriaTypeOptions.national_champion_denmark: 'national-championship-denmark',
                AwardBase.CriteriaTypeOptions.national_champion_italy: 'national-championship-italy',
                AwardBase.CriteriaTypeOptions.national_champion_netherlands: 'national-championship-netherlands',
                AwardBase.CriteriaTypeOptions.national_champion_poland: 'national-championship-poland',
                AwardBase.CriteriaTypeOptions.national_champion_portugal: 'national-championship-portugal',
                AwardBase.CriteriaTypeOptions.national_champion_south_korea: 'national-championship-south-korea',
                AwardBase.CriteriaTypeOptions.national_champion_sweden: 'national-championship-sweden',
                AwardBase.CriteriaTypeOptions.national_champion_taiwan: 'national-championship-taiwan',
                AwardBase.CriteriaTypeOptions.national_champion_united_kingdom: 'national-championship-united-kingdom',
                AwardBase.CriteriaTypeOptions.national_champion_united_states: 'national-championship-united-states',
                AwardBase.CriteriaTypeOptions.national_champion_france: 'national-championship-france',
                AwardBase.CriteriaTypeOptions.national_champion_chile: 'national-championship-chile',
                AwardBase.CriteriaTypeOptions.national_champion_germany: 'national-championship-germany',
                AwardBase.CriteriaTypeOptions.national_champion_greece: 'national-championship-greece'
            }.get(criteria_type, None)
            if tag_slug:
                value = qs.filter(
                    event__is_casual=False,
                    finishing_position=1,
                    event__tags__slug=tag_slug
                ).count()

        value += AwardCredit.objects.filter(
            user=user,
            criteria=criteria_type
        ).aggregate(total=Coalesce(Sum('amount'), 0))['total'] or 0

        return value


class Feature(models.Model):
    class Keys:
        LADDERS = 'ladders'

    key = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(default=None, null=True, blank=True)
    is_enabled = models.BooleanField(
        default=False,
        help_text=_('Applies to every playgroup without its own override.'))

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PlaygroupFeature(models.Model):
    playgroup = models.ForeignKey(
        Playgroup, on_delete=models.CASCADE, related_name='feature_overrides')
    feature = models.ForeignKey(
        Feature, on_delete=models.CASCADE, related_name='playgroup_overrides')
    is_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['playgroup', 'feature'],
                             name='unique_playgroup_feature'),
        ]

    def __str__(self):
        return f'{self.playgroup} - {self.feature}'


class LadderRuleViolation(Exception):
    pass


class Match(models.Model):
    playgroup = models.ForeignKey(
        Playgroup, on_delete=models.CASCADE, related_name='matches')
    player_one = models.ForeignKey(
        PlaygroupMember, on_delete=models.CASCADE, related_name='matches_as_player_one')
    player_two = models.ForeignKey(
        PlaygroupMember, on_delete=models.CASCADE, related_name='matches_as_player_two')
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Matches'
        ordering = ['created_on']
        constraints = [
            models.CheckConstraint(
                condition=~Q(player_one=F('player_two')),
                name='pmc_match_distinct_players'),
        ]

    def __str__(self):
        return f'{self.player_one} vs {self.player_two}'

    def has_result(self):
        return hasattr(self, 'result')

    def involves(self, member):
        return member.pk in (self.player_one_id, self.player_two_id)


class MatchResult(models.Model):
    match = models.OneToOneField(
        Match, on_delete=models.CASCADE, related_name='result')
    winner = models.ForeignKey(
        PlaygroupMember, on_delete=models.CASCADE, related_name='match_wins',
        default=None, null=True, blank=True)
    player_one_score = models.PositiveIntegerField(
        default=None, null=True, blank=True)
    player_two_score = models.PositiveIntegerField(
        default=None, null=True, blank=True)
    is_forfeit = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, related_name='+',
        default=None, null=True, blank=True)
    voided_on = models.DateTimeField(default=None, null=True, blank=True)
    voided_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, related_name='+',
        default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_on']

    def __str__(self):
        if self.winner:
            return f'{self.winner} wins - {self.match}'
        return f'Tie - {self.match}'

    def is_tie(self):
        return self.winner_id is None

    def is_voided(self):
        return self.voided_on is not None

    def get_loser(self):
        if self.is_tie():
            return None
        if self.winner_id == self.match.player_one_id:
            return self.match.player_two
        return self.match.player_one


LadderStanding = namedtuple('LadderStanding', [
    'rank', 'entry', 'is_viewer', 'can_be_challenged', 'challenge_block_reason', 'has_open_challenge'])


class Ladder(models.Model):
    playgroup = models.ForeignKey(
        Playgroup, on_delete=models.CASCADE, related_name='ladders')
    name = models.CharField(max_length=100)
    challenges_enabled = models.BooleanField(
        default=True,
        help_text=_('When disabled, only EOs can change positions on this ladder.'))
    challenge_range = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1)],
        help_text=_('How many places above themselves a player may challenge.'))
    open_challenge_limit = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1)],
        help_text=_('The most open challenges a player may be part of at once, issued or received.'))
    response_window_days = models.PositiveSmallIntegerField(
        default=7, validators=[MinValueValidator(1)],
        help_text=_('Days to record a result before the challenger wins by forfeit.'))
    created_on = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, related_name='+',
        default=None, null=True, blank=True)

    class Meta:
        ordering = ['name']
        constraints = [
            UniqueConstraint(fields=['playgroup', 'name'],
                             name='unique_ladder_name_per_playgroup'),
        ]

    def __str__(self):
        return self.name

    def is_organizer(self, user):
        return self.playgroup.members.filter(user=user, is_staff=True).exists()

    def get_ordered_entries(self):
        return list(self.entries.select_related(
            'member__user__pmc_profile__avatar').order_by('position', 'pk'))

    def get_rank_of(self, member):
        ranked_member_ids = [entry.member_id for entry in self.get_ordered_entries()]
        if member is None or member.pk not in ranked_member_ids:
            return None
        return ranked_member_ids.index(member.pk) + 1

    def get_open_challenges(self):
        return self.challenges.filter(
            status=LadderChallenge.ChallengeStatuses.PENDING
        ).select_related(
            'match__player_one__user', 'match__player_two__user'
        ).order_by('respond_by', 'pk')

    def get_recent_results(self, limit=10):
        return self.challenges.filter(
            match__result__isnull=False
        ).select_related(
            'match__result__winner__user', 'match__player_one__user', 'match__player_two__user'
        ).order_by('-resolved_on', '-pk')[:limit]

    def get_challenge_ineligibility_reason(self, challenger, defender):
        return self._challenge_ineligibility_reason(
            [entry.member_id for entry in self.get_ordered_entries()],
            list(self.get_open_challenges()),
            challenger,
            defender,
        )

    def get_standings_for(self, viewer_member):
        entries = self.get_ordered_entries()
        ranked_member_ids = [entry.member_id for entry in entries]
        open_challenges = list(self.get_open_challenges())
        members_with_open_challenges = {
            member_id
            for challenge in open_challenges
            for member_id in (challenge.match.player_one_id, challenge.match.player_two_id)
        }
        viewer_index = None
        if viewer_member is not None and viewer_member.pk in ranked_member_ids:
            viewer_index = ranked_member_ids.index(viewer_member.pk)

        standings = []
        for index, entry in enumerate(entries):
            is_within_viewer_reach = (
                self.challenges_enabled
                and viewer_index is not None
                and 0 < viewer_index - index <= self.challenge_range
            )
            challenge_block_reason = None
            if is_within_viewer_reach:
                challenge_block_reason = self._challenge_ineligibility_reason(
                    ranked_member_ids, open_challenges, viewer_member, entry.member)
            standings.append(LadderStanding(
                rank=index + 1,
                entry=entry,
                is_viewer=index == viewer_index,
                can_be_challenged=is_within_viewer_reach and challenge_block_reason is None,
                challenge_block_reason=challenge_block_reason,
                has_open_challenge=entry.member_id in members_with_open_challenges,
            ))
        return standings

    def add_member(self, member, rank=None):
        self._ensure_playgroup_member(member)
        with self._ordered_entries_for_update() as entries:
            if self._find_entry(entries, member):
                raise LadderRuleViolation(
                    _('%(name)s is already on this ladder.') % {'name': member})
            entry = LadderEntry.objects.create(
                ladder=self, member=member, position=len(entries) + 1)
            entries.insert(self._index_for_rank(rank, entries), entry)
            return entry

    def move_member(self, member, rank):
        with self._ordered_entries_for_update() as entries:
            entry = self._require_entry(entries, member)
            entries.remove(entry)
            entries.insert(self._index_for_rank(rank, entries), entry)

    def remove_member(self, member):
        with self._ordered_entries_for_update() as entries:
            entry = self._require_entry(entries, member)
            self._close_open_challenges_for_departing(member)
            entries.remove(entry)
            entry.delete()

    def issue_challenge(self, challenger, defender):
        with self._ordered_entries_for_update() as entries:
            reason = self._challenge_ineligibility_reason(
                [entry.member_id for entry in entries],
                list(self.get_open_challenges()),
                challenger,
                defender,
            )
            if reason:
                raise LadderRuleViolation(reason)
            match = Match.objects.create(
                playgroup_id=self.playgroup_id, player_one=challenger, player_two=defender)
            return LadderChallenge.objects.create(
                ladder=self,
                match=match,
                respond_by=timezone.now() + timedelta(days=self.response_window_days),
            )

    def record_result(self, challenge, winner, recorded_by):
        self._ensure_participant_or_organizer(challenge, recorded_by)
        with self._ordered_entries_for_update() as entries:
            challenge = self._reload_pending_challenge(challenge)
            if winner is not None and not challenge.match.involves(winner):
                raise LadderRuleViolation(
                    _('The winner must be one of the players in this challenge.'))
            MatchResult.objects.create(
                match=challenge.match, winner=winner, recorded_by=recorded_by)
            challenge.mark_resolved(LadderChallenge.ChallengeStatuses.COMPLETED)
            if winner is not None and winner.pk == challenge.match.player_one_id:
                self._move_challenger_ahead_of_defender(entries, challenge.match)

    def withdraw_challenge(self, challenge, acting_user):
        is_challenger = challenge.match.player_one.user_id == acting_user.pk
        if not is_challenger and not self.is_organizer(acting_user):
            raise PermissionDenied
        with self._ordered_entries_for_update():
            challenge = self._reload_pending_challenge(challenge)
            challenge.mark_resolved(LadderChallenge.ChallengeStatuses.WITHDRAWN)

    def void_challenge(self, challenge, acting_user):
        if not self.is_organizer(acting_user):
            raise PermissionDenied
        with self._ordered_entries_for_update():
            challenge = LadderChallenge.objects.select_related(
                'match').get(pk=challenge.pk, ladder=self)
            if challenge.status in (LadderChallenge.ChallengeStatuses.WITHDRAWN, LadderChallenge.ChallengeStatuses.VOIDED):
                raise LadderRuleViolation(
                    _('This challenge has already been withdrawn or voided.'))
            if challenge.match.has_result():
                challenge.match.result.voided_on = timezone.now()
                challenge.match.result.voided_by = acting_user
                challenge.match.result.save()
            challenge.mark_resolved(LadderChallenge.ChallengeStatuses.VOIDED)

    def void_open_challenges(self):
        self.challenges.filter(
            status=LadderChallenge.ChallengeStatuses.PENDING
        ).update(status=LadderChallenge.ChallengeStatuses.VOIDED, resolved_on=timezone.now())

    def resolve_overdue_challenges(self):
        if not self._get_overdue_challenges().exists():
            return
        with transaction.atomic():
            Ladder.objects.select_for_update().get(pk=self.pk)
            entries = self.get_ordered_entries()
            self._forfeit_overdue_challenges(entries)
            self._save_positions(entries)

    @contextmanager
    def _ordered_entries_for_update(self):
        self.resolve_overdue_challenges()
        with transaction.atomic():
            Ladder.objects.select_for_update().get(pk=self.pk)
            entries = self.get_ordered_entries()
            self._forfeit_overdue_challenges(entries)
            yield entries
            self._save_positions(entries)

    def _forfeit_overdue_challenges(self, entries):
        for challenge in self._get_overdue_challenges().select_related('match').order_by('respond_by', 'pk'):
            self._resolve_by_forfeit(challenge, entries)

    def _save_positions(self, entries):
        repositioned_entries = []
        for position, entry in enumerate(entries, start=1):
            if entry.position != position:
                entry.position = position
                repositioned_entries.append(entry)
        LadderEntry.objects.bulk_update(repositioned_entries, ['position'])

    def _get_overdue_challenges(self):
        return self.challenges.filter(
            status=LadderChallenge.ChallengeStatuses.PENDING,
            respond_by__lt=timezone.now(),
        )

    def _resolve_by_forfeit(self, challenge, entries):
        MatchResult.objects.create(
            match=challenge.match, winner_id=challenge.match.player_one_id, is_forfeit=True)
        challenge.mark_resolved(LadderChallenge.ChallengeStatuses.FORFEITED)
        self._move_challenger_ahead_of_defender(entries, challenge.match)

    def _move_challenger_ahead_of_defender(self, entries, match):
        challenger_entry = self._find_entry(entries, match.player_one)
        defender_entry = self._find_entry(entries, match.player_two)
        if challenger_entry is None or defender_entry is None:
            return
        defender_index = entries.index(defender_entry)
        if entries.index(challenger_entry) < defender_index:
            return
        entries.remove(challenger_entry)
        entries.insert(defender_index, challenger_entry)

    def _close_open_challenges_for_departing(self, member):
        open_challenges = self.challenges.filter(
            status=LadderChallenge.ChallengeStatuses.PENDING)
        now = timezone.now()
        open_challenges.filter(match__player_one=member).update(
            status=LadderChallenge.ChallengeStatuses.WITHDRAWN, resolved_on=now)
        open_challenges.filter(match__player_two=member).update(
            status=LadderChallenge.ChallengeStatuses.VOIDED, resolved_on=now)

    def _reload_pending_challenge(self, challenge):
        challenge = LadderChallenge.objects.select_related(
            'match').get(pk=challenge.pk, ladder=self)
        if challenge.status == LadderChallenge.ChallengeStatuses.FORFEITED:
            raise LadderRuleViolation(
                _('The response window has passed, so the challenger won by forfeit.'))
        if challenge.status != LadderChallenge.ChallengeStatuses.PENDING:
            raise LadderRuleViolation(
                _('This challenge has already been resolved.'))
        return challenge

    def _ensure_playgroup_member(self, member):
        if member.playgroup_id != self.playgroup_id:
            raise LadderRuleViolation(
                _('%(name)s is not a member of this playgroup.') % {'name': member})

    def _ensure_participant_or_organizer(self, challenge, user):
        participant_user_ids = (
            challenge.match.player_one.user_id, challenge.match.player_two.user_id)
        if user.pk not in participant_user_ids and not self.is_organizer(user):
            raise PermissionDenied

    def _require_entry(self, entries, member):
        entry = self._find_entry(entries, member)
        if entry is None:
            raise LadderRuleViolation(
                _('%(name)s is not on this ladder.') % {'name': member})
        return entry

    @staticmethod
    def _find_entry(entries, member):
        return next((entry for entry in entries if entry.member_id == member.pk), None)

    @staticmethod
    def _index_for_rank(rank, entries):
        if rank is None:
            return len(entries)
        return min(max(rank, 1), len(entries) + 1) - 1

    def _challenge_ineligibility_reason(self, ranked_member_ids, open_challenges, challenger, defender):
        if not self.challenges_enabled:
            return _('Challenges are disabled on this ladder.')
        if challenger.pk not in ranked_member_ids:
            return _('Join the ladder before issuing challenges.')
        if defender.pk not in ranked_member_ids:
            return _('That player is not on this ladder.')
        if challenger.pk == defender.pk:
            return _('You cannot challenge yourself.')

        places_above_challenger = ranked_member_ids.index(
            challenger.pk) - ranked_member_ids.index(defender.pk)
        if places_above_challenger < 1:
            return _('You can only challenge players ranked above you.')
        if places_above_challenger > self.challenge_range:
            return _('You can only challenge players up to %(range)s places above you.') % {
                'range': self.challenge_range}

        if any(challenge.match.involves(challenger) and challenge.match.involves(defender) for challenge in open_challenges):
            return _('You already have an open challenge with %(name)s.') % {'name': defender}

        def count_open_challenges_involving(member):
            return sum(1 for challenge in open_challenges if challenge.match.involves(member))

        if count_open_challenges_involving(challenger) >= self.open_challenge_limit:
            return _('You have reached your limit of open challenges.')
        if count_open_challenges_involving(defender) >= self.open_challenge_limit:
            return _('%(name)s has reached their limit of open challenges.') % {'name': defender}
        return None


class LadderEntry(models.Model):
    ladder = models.ForeignKey(
        Ladder, on_delete=models.CASCADE, related_name='entries')
    member = models.ForeignKey(
        PlaygroupMember, on_delete=models.CASCADE, related_name='ladder_entries')
    position = models.PositiveIntegerField()
    joined_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Ladder entries'
        ordering = ['position', 'pk']
        constraints = [
            UniqueConstraint(fields=['ladder', 'member'],
                             name='unique_ladder_entry_member'),
        ]

    def __str__(self):
        return f'{self.ladder} - #{self.position} {self.member}'


class LadderChallenge(models.Model):
    class ChallengeStatuses(models.IntegerChoices):
        PENDING = (0, _('Pending'))
        COMPLETED = (1, _('Completed'))
        FORFEITED = (2, _('Won by Forfeit'))
        WITHDRAWN = (3, _('Withdrawn'))
        VOIDED = (4, _('Voided'))

    ladder = models.ForeignKey(
        Ladder, on_delete=models.CASCADE, related_name='challenges')
    match = models.OneToOneField(
        Match, on_delete=models.CASCADE, related_name='ladder_challenge')
    status = models.IntegerField(
        choices=ChallengeStatuses.choices, default=ChallengeStatuses.PENDING)
    issued_on = models.DateTimeField(auto_now_add=True)
    respond_by = models.DateTimeField()
    resolved_on = models.DateTimeField(default=None, null=True, blank=True)

    class Meta:
        ordering = ['-issued_on']

    def __str__(self):
        return f'{self.ladder} - {self.match}'

    @property
    def challenger(self):
        return self.match.player_one

    @property
    def defender(self):
        return self.match.player_two

    def is_pending(self):
        return self.status == self.ChallengeStatuses.PENDING

    def is_overdue(self):
        return self.is_pending() and self.respond_by < timezone.now()

    def mark_resolved(self, status):
        self.status = status
        self.resolved_on = timezone.now()
        self.save(update_fields=['status', 'resolved_on'])
