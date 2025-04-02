from tokenize import blank_re
from django import forms
from pkg_resources import require
from .models import Event, LeaderboardSeason, LeaderboardSeasonPeriod, Playgroup, PmcProfile
from .models import PlaygroupMember
from .models import EventFormat
from django.utils.translation import gettext_lazy as _


class EventForm(forms.ModelForm):
    results_file = forms.FileField(required=True)
    format = forms.ModelChoiceField(
        queryset=EventFormat.objects.all(),
        empty_label=_('Other'),
        required=False
    )

    class Meta:
        model = Event
        fields = ('name', 'start_date', 'format', 'player_count')
        labels = {
            'name': _('Event Name'),
            'start_date': _('Event Date'),
            'player_count': _('Player Count'),
        }
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'player_count': forms.NumberInput(attrs={
                'min': 0,
                'placeholder': _('Automatic')
            }),
        }

    def save(self, commit=True):
        event = super(EventForm, self).save(commit=commit)
        return event


class PlaygroupForm(forms.ModelForm):
    class Meta:
        model = Playgroup
        fields = ('name', 'slug', 'type', 'description')


class PlaygroupMemberForm(forms.ModelForm):
    class Meta:
        model = PlaygroupMember
        fields = ('nickname',)


class PmcProfileForm(forms.ModelForm):
    class Meta:
        model = PmcProfile
        fields = ('pronouns', 'tagline',)


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
