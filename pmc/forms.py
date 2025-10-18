from django import forms

from decks.models import Deck
from .models import Event, LeaderboardSeason, LeaderboardSeasonPeriod, Playgroup, PlaygroupJoinRequest, PmcProfile
from .models import PlaygroupMember
from .models import EventFormat
from django.utils.translation import gettext_lazy as _


class EventForm(forms.ModelForm):
    results_file = forms.FileField(
        required=False, help_text=_('This file is optional. See below for details.'))
    format = forms.ModelChoiceField(
        queryset=EventFormat.objects.all(),
        empty_label=_('Other'),
        required=False
    )
    start_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label=_('Event Date')
    )

    class Meta:
        model = Event
        fields = ('name', 'start_date', 'is_casual', 'is_digital', 'format',
                  'player_count', 'is_excluded_from_global_rankings')
        labels = {
            'name': _('Event Name'),
            'player_count': _('Player Count'),
            'is_casual': _('Event Type'),
            'is_digital': _('Event Mode'),
            'is_excluded_from_global_rankings': _('PG Only RP'),
        }
        widgets = {
            'player_count': forms.NumberInput(attrs={
                'min': 2,
            }),
            'is_digital': forms.Select(choices=[
                (False, _('In-Person')),
                (True, _('Online')),
            ])
        }
        help_texts = {
            'is_excluded_from_global_rankings': _('If checked, this event will not contribute RP towards global leaderboards. Only available to Django staff.'),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.playgroup = kwargs.pop('playgroup', None)
        super().__init__(*args, **kwargs)

        if not (self.user and self.user.is_staff):
            self.fields.pop('is_excluded_from_global_rankings', None)

        if self.playgroup:
            self.fields['is_digital'].initial = self.playgroup.event_default_is_digital

    def save(self, commit=True):
        event = super(EventForm, self).save(commit=False)

        if not (self.user and self.user.is_staff):
            event.is_excluded_from_global_rankings = False

        if commit:
            event.save()
        return event


class EventUpdateForm(forms.ModelForm):
    start_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label=_('Event Date')
    )

    class Meta:
        model = Event
        fields = ('name', 'start_date', 'is_casual', 'is_digital', 'format',
                  'player_count', 'is_excluded_from_global_rankings')
        labels = {
            'name': _('Event Name'),
            'player_count': _('Player Count'),
            'is_casual': _('Event Type'),
            'is_digital': _('Event Mode'),
            'is_excluded_from_global_rankings': _('PG Only RP'),
        }
        widgets = {
            'player_count': forms.NumberInput(attrs={
                'min': 2,
            }),
            'is_digital': forms.Select(choices=[
                (False, _('In-Person')),
                (True, _('Online')),
            ])
        }
        help_texts = {
            'is_excluded_from_global_rankings': _('If checked, this event will not contribute RP towards global leaderboards. Only available to Django staff.'),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Hide global rankings exclusion field for non-staff users
        if not (self.user and self.user.is_staff):
            self.fields.pop('is_excluded_from_global_rankings', None)

    def save(self, commit=True):
        event = super().save(commit=False)

        # Only allow staff users to modify the global rankings exclusion field
        if not (self.user and self.user.is_staff):
            # Preserve the existing value if user is not staff
            if self.instance.pk:
                original_event = Event.objects.get(pk=self.instance.pk)
                event.is_excluded_from_global_rankings = original_event.is_excluded_from_global_rankings
            else:
                event.is_excluded_from_global_rankings = False

        if commit:
            event.save()
        return event


class EventResultDeckForm(forms.ModelForm):
    deck_link = forms.URLField(required=True, help_text=_('MV or DoK URL'))

    class Meta:
        model = Deck
        fields = ()

    def clean(self):
        cleaned_data = super().clean()
        deck_link = cleaned_data.get('deck_link')
        deck = Deck(
            id=Deck.get_id_from_master_vault_url(deck_link)
        )
        deck.hydrate_from_master_vault(save=False)
        self.instance, _created = Deck.objects.get_or_create(
            id=deck.id,
            defaults={
                'name': deck.name,
                'set': deck.set,
                'house_1': deck.house_1,
                'house_2': deck.house_2,
                'house_3': deck.house_3
            }
        )
        return cleaned_data


class PlaygroupForm(forms.ModelForm):
    class Meta:
        model = Playgroup
        fields = ('name', 'slug', 'type',
                  'event_default_is_digital', 'description')
        widgets = {
            'event_default_is_digital': forms.Select(choices=[
                (False, _('In-Person')),
                (True, _('Online')),
            ])
        }


class PlaygroupMemberForm(forms.ModelForm):
    class Meta:
        model = PlaygroupMember
        fields = ('nickname',)


class PlaygroupJoinRequestForm(forms.ModelForm):
    class Meta:
        model = PlaygroupJoinRequest
        fields = ('note',)
        widgets = {
            'note': forms.Textarea(
                attrs={
                    'rows': 3,
                    'placeholder': _('An optional note to the playgroup EOs.')
                }
            )
        }


class PmcProfileForm(forms.ModelForm):
    class Meta:
        model = PmcProfile
        fields = ('pronouns', 'theme', 'tagline',)


class PmcProfilePrivacyForm(forms.ModelForm):
    class Meta:
        model = PmcProfile
        fields = ('show_stats_on_profile', 'show_awards_on_profile',
                  'show_playgroups_on_profile',)
        widgets = {
            'show_stats_on_profile': forms.Select(
                choices=[
                    (False, _('Private, do not show')),
                    (True, _('Public, show to everyone')),
                ]
            ),
            'show_awards_on_profile': forms.Select(
                choices=[
                    (False, _('Private, do not show')),
                    (True, _('Public, show to everyone')),
                ]
            ),
            'show_playgroups_on_profile': forms.Select(
                choices=[
                    (False, _('Private, do not show')),
                    (True, _('Public, show to everyone')),
                ]
            ),
        }


class LeaderboardSeasonPeriodForm(forms.Form):
    season = forms.ModelChoiceField(
        queryset=LeaderboardSeason.objects.none(),
        initial=LeaderboardSeason.objects.first(),
        required=True,
        widget=forms.Select(attrs={'onchange': 'this.closest("form").submit()'}))
    period = forms.ModelChoiceField(
        queryset=LeaderboardSeasonPeriod.objects.none(),
        initial=LeaderboardSeasonPeriod.objects.first(),
        required=True,
        widget=forms.Select(attrs={'onchange': 'this.closest("form").submit()'}))

    def __init__(self, leaderboard, *args, **kwargs):
        super().__init__(*args, **kwargs)
        season_qs = LeaderboardSeason.objects.filter(
            periods__frequency=leaderboard.period_frequency
        ).distinct()
        self.fields['season'].queryset = season_qs

        if 'season' in self.data:
            try:
                season_id = int(self.data.get('season'))
                period_qs = LeaderboardSeasonPeriod.objects.filter(
                    season_id=season_id, frequency=leaderboard.period_frequency)
                self.fields['period'].queryset = period_qs
                if 'period' not in self.data:
                    self.fields['period'].initial = period_qs.first()
            except (ValueError, TypeError):
                pass
        else:
            initial_season = season_qs.first()
            self.fields['season'].initial = initial_season

            period_qs = LeaderboardSeasonPeriod.objects.filter(
                season=initial_season, frequency=leaderboard.period_frequency)
            self.fields['period'].queryset = period_qs
            self.fields['period'].initial = period_qs.first()

        if leaderboard.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.ALL_TIME:
            self.fields.pop('season')
            self.fields.pop('period')
        elif leaderboard.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.SEASON:
            self.fields.pop('period')
