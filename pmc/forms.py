from django import forms
from django.utils.safestring import mark_safe

from decks.models import Deck
from .models import Event, EventTag, LeaderboardSeason, LeaderboardSeasonPeriod, Playgroup, PlaygroupJoinRequest, PmcProfile, RankingPointsMapVersion
from .models import PlaygroupMember
from .models import Venue
from .models import EventFormat
from .models import Ladder
from .models import BoxLeague
from django.db.models import Max
from django.utils.translation import gettext_lazy as _


class EmptyableCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    empty_message = _('No options available.')

    def __init__(self, *args, empty_message=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empty_message is not None:
            self.empty_message = empty_message

    def render(self, name, value, attrs=None, renderer=None):
        if not self.choices:
            return mark_safe(f'<span class="form-empty-message">{self.empty_message}</span>')
        return super().render(name, value, attrs, renderer)


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
    tags = forms.ModelMultipleChoiceField(
        queryset=EventTag.objects.all(),
        required=False,
        widget=EmptyableCheckboxSelectMultiple(
            empty_message=_('No tags available.')),
        label=_('Tags')
    )

    class Meta:
        model = Event
        fields = ('name', 'description', 'start_date', 'is_casual', 'is_digital',
                  'format', 'player_count', 'tags', 'is_accepting_registrations',
                  'is_excluded_from_global_rankings')
        labels = {
            'name': _('Event Name'),
            'player_count': _('Player Count'),
            'is_casual': _('Event Type'),
            'is_digital': _('Event Mode'),
            'is_accepting_registrations': _('Accept Registrations'),
            'is_excluded_from_global_rankings': _('PG Only RP'),
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'player_count': forms.NumberInput(attrs={
                'min': 0,
            }),
            'is_digital': forms.Select(choices=[
                (False, _('In-Person')),
                (True, _('Online')),
            ])
        }
        help_texts = {
            'is_accepting_registrations': _('Allow members to register for this event in advance.'),
            'is_excluded_from_global_rankings': _('If checked, this event will not contribute RP towards global leaderboards. Only available to Django staff.'),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.playgroup = kwargs.pop('playgroup', None)
        super().__init__(*args, **kwargs)

        if not (self.user and self.user.is_staff):
            self.fields.pop('is_excluded_from_global_rankings', None)
            self.fields['tags'].queryset = EventTag.objects.filter(
                is_eo_assignable=True)

        if self.playgroup:
            self.fields['is_digital'].initial = self.playgroup.event_default_is_digital

    def save(self, commit=True):
        event = super(EventForm, self).save(commit=False)

        if not (self.user and self.user.is_staff):
            event.is_excluded_from_global_rankings = False

        if commit:
            event.save()
            self.save_m2m()
        return event


class EventUpdateForm(forms.ModelForm):
    start_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label=_('Event Date')
    )
    tags = forms.ModelMultipleChoiceField(
        queryset=EventTag.objects.all(),
        required=False,
        widget=EmptyableCheckboxSelectMultiple(
            empty_message=_('No tags available.')),
        label=_('Tags')
    )

    class Meta:
        model = Event
        fields = ('name', 'description', 'start_date', 'is_casual', 'is_digital',
                  'format', 'player_count', 'is_accepting_registrations',
                  'is_excluded_from_global_rankings', 'tags')
        labels = {
            'name': _('Event Name'),
            'player_count': _('Player Count'),
            'is_casual': _('Event Type'),
            'is_digital': _('Event Mode'),
            'is_accepting_registrations': _('Accept Registrations'),
            'is_excluded_from_global_rankings': _('PG Only RP'),
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'player_count': forms.NumberInput(attrs={
                'min': 0,
            }),
            'is_digital': forms.Select(choices=[
                (False, _('In-Person')),
                (True, _('Online')),
            ])
        }
        help_texts = {
            'is_accepting_registrations': _('Allow members to register for this event in advance.'),
            'is_excluded_from_global_rankings': _('If checked, this event will not contribute RP towards global leaderboards. Only available to Django staff.'),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if not (self.user and self.user.is_staff):
            self.fields.pop('is_excluded_from_global_rankings', None)
            self.fields['tags'].queryset = EventTag.objects.filter(
                is_eo_assignable=True)

    def save(self, commit=True):
        event = super().save(commit=False)

        if not (self.user and self.user.is_staff):
            if self.instance.pk:
                original_event = Event.objects.get(pk=self.instance.pk)
                event.is_excluded_from_global_rankings = original_event.is_excluded_from_global_rankings
            else:
                event.is_excluded_from_global_rankings = False

        if commit:
            event.save()
            self.save_m2m()
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
        required=True,
        empty_label=None,
        widget=forms.Select(attrs={'onchange': 'this.closest("form").submit()'}))
    period = forms.ModelChoiceField(
        queryset=LeaderboardSeasonPeriod.objects.none(),
        required=True,
        empty_label=None,
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
                if 'period' in self.data:
                    period_id = int(self.data.get('period'))
                    try:
                        self.fields['period'].initial = period_qs.get(
                            id=period_id)
                    except LeaderboardSeasonPeriod.DoesNotExist:
                        self.fields['period'].initial = period_qs.first()
                else:
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


class RankingPointsMapVersionForm(forms.Form):
    version = forms.ModelChoiceField(
        queryset=RankingPointsMapVersion.objects.all().order_by('-effective_on'),
        required=True,
        label=_('Version'),
        widget=forms.Select(
            attrs={'onchange': 'this.closest("form").submit()'})
    )


class VenueForm(forms.ModelForm):
    class Meta:
        model = Venue
        fields = ('name', 'address')
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
        help_texts = {
            'address': _('Enter the full address as it would appear on mail.'),
        }


class UniqueNameInPlaygroupForm(forms.ModelForm):
    duplicate_name_message = None

    def __init__(self, *args, playgroup, **kwargs):
        super().__init__(*args, **kwargs)
        self.playgroup = playgroup

    def clean_name(self):
        name = self.cleaned_data['name']
        same_named_objects = self._meta.model.objects.filter(
            playgroup=self.playgroup, name__iexact=name).exclude(pk=self.instance.pk)
        if same_named_objects.exists():
            raise forms.ValidationError(self.duplicate_name_message)
        return name


class LadderForm(UniqueNameInPlaygroupForm):
    duplicate_name_message = _('This playgroup already has a ladder with that name.')

    class Meta:
        model = Ladder
        fields = ('name', 'description', 'challenges_enabled', 'challenge_range',
                  'open_challenge_limit', 'response_window_days', 'rematch_cooldown_days',
                  'discord_webhook_url')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }


class LadderPlayedResultForm(forms.Form):
    I_WON = 'won'
    THEY_WON = 'lost'
    TIE = 'tie'

    opponent = forms.ModelChoiceField(
        queryset=PlaygroupMember.objects.none(), label=_('Opponent'))
    outcome = forms.ChoiceField(
        widget=forms.RadioSelect,
        label=_('Result'),
        choices=[(I_WON, _('I won')), (THEY_WON, _('They won')), (TIE, _('Tie'))],
    )

    def __init__(self, *args, ladder, member, **kwargs):
        super().__init__(*args, **kwargs)
        self.member = member
        self.fields['opponent'].queryset = PlaygroupMember.objects.filter(
            pk__in=[opponent.pk for opponent in ladder.get_played_result_opponents(member)]
        ).select_related('user').order_by('user__username')

    def get_winner(self):
        return {
            self.I_WON: self.member,
            self.THEY_WON: self.cleaned_data['opponent'],
            self.TIE: None,
        }[self.cleaned_data['outcome']]


class LadderAddMemberForm(forms.Form):
    member = forms.ModelChoiceField(
        queryset=PlaygroupMember.objects.none(), label=_('Player'))
    position = forms.IntegerField(
        min_value=1, required=False,
        help_text=_('Leave blank to add the player at the bottom.'))

    def __init__(self, *args, ladder, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['member'].queryset = ladder.playgroup.members.exclude(
            ladder_entries__ladder=ladder
        ).select_related('user').order_by('user__username')


class LadderMoveMemberForm(forms.Form):
    position = forms.IntegerField(min_value=1)


class MatchOutcomeForm(forms.Form):
    PLAYER_ONE_WON = 'player_one'
    PLAYER_TWO_WON = 'player_two'
    TIE = 'tie'
    PLAYER_WON_LABEL = _('%(name)s won')

    outcome = forms.ChoiceField(widget=forms.RadioSelect, label=_('Result'))

    def __init__(self, *args, match, player_one_won_label=PLAYER_WON_LABEL, **kwargs):
        super().__init__(*args, **kwargs)
        self.match = match
        self.fields['outcome'].choices = [
            (self.PLAYER_ONE_WON, player_one_won_label % {'name': match.player_one}),
            (self.PLAYER_TWO_WON, self.PLAYER_WON_LABEL % {'name': match.player_two}),
            (self.TIE, _('Tie')),
        ]

    @classmethod
    def initial_for(cls, result):
        if result.is_tie():
            return {'outcome': cls.TIE}
        if result.winner_id == result.match.player_one_id:
            return {'outcome': cls.PLAYER_ONE_WON}
        return {'outcome': cls.PLAYER_TWO_WON}

    def get_winner(self):
        return {
            self.PLAYER_ONE_WON: self.match.player_one,
            self.PLAYER_TWO_WON: self.match.player_two,
            self.TIE: None,
        }[self.cleaned_data['outcome']]


class BoxLeagueForm(UniqueNameInPlaygroupForm):
    duplicate_name_message = _('This playgroup already has a box league with that name.')

    class Meta:
        model = BoxLeague
        fields = ('name', 'layout', 'target_box_size', 'promotion_count',
                  'relegation_count', 'session_length_months')
        labels = {
            'target_box_size': _('Players per box'),
            'promotion_count': _('Moving up'),
            'relegation_count': _('Moving down'),
            'session_length_months': _('Session length (months)'),
        }


class BoxLeagueTierNameForm(forms.Form):
    name = forms.CharField(max_length=50, required=False)


class BaseBoxLeagueTierNameFormSet(forms.BaseFormSet):
    def get_tier_names(self):
        tier_names = [
            form.cleaned_data.get('name', '').strip()
            for form in self.forms
            if not form.cleaned_data.get('DELETE')
        ]
        while tier_names and not tier_names[-1]:
            tier_names.pop()
        return tier_names


BoxLeagueTierNameFormSet = forms.formset_factory(
    BoxLeagueTierNameForm, formset=BaseBoxLeagueTierNameFormSet, extra=1, can_delete=True)


class BoxProposalResizeForm(forms.Form):
    box_count = forms.IntegerField(min_value=1, max_value=128, label=_('Boxes this session'))


class BoxAddForm(forms.Form):
    level = forms.TypedChoiceField(coerce=int, label=_('Tier'))

    def __init__(self, *args, session, **kwargs):
        super().__init__(*args, **kwargs)
        tier_names_by_level = session.league.get_tier_names_by_level()
        bottom_level = session.boxes.aggregate(bottom=Max('level'))['bottom'] or 0
        self.fields['level'].choices = [
            (level, session.league.get_tier_name(level, tier_names_by_level))
            for level in range(1, bottom_level + 1)
        ] + [(bottom_level + 1, _('New bottom tier'))]


class BoxLeagueAddMemberForm(forms.Form):
    member = forms.ModelChoiceField(
        queryset=PlaygroupMember.objects.none(), label=_('Player'))

    def __init__(self, *args, league, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['member'].queryset = league.playgroup.members.exclude(
            box_league_entries__league=league
        ).select_related('user').order_by('user__username')


class BoxAssignmentForm(forms.Form):
    member = forms.ModelChoiceField(
        queryset=PlaygroupMember.objects.none(), label=_('Player'))
    box = forms.ChoiceField(label=_('Box'))

    def __init__(self, *args, session, box_summaries, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self.fields['member'].queryset = session.league.playgroup.members.select_related(
            'user').order_by('user__username')
        self.fields['member'].help_text = _('Players not yet in the league are added to it.')
        self.fields['box'].choices = [
            (summary.box.pk, summary.name) for summary in box_summaries]

    def get_box(self):
        return self.session.boxes.get(pk=self.cleaned_data['box'])


class BoxSessionStartForm(forms.Form):
    starts_on = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    ends_on = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text=_('Advertised to players; the session stays open until the next one starts.'))

    def clean(self):
        cleaned_data = super().clean()
        starts_on = cleaned_data.get('starts_on')
        ends_on = cleaned_data.get('ends_on')
        if starts_on and ends_on and ends_on < starts_on:
            raise forms.ValidationError(_('The session must end on or after its start date.'))
        return cleaned_data
