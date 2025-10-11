from django import forms
from django.contrib.auth.models import User
from .models import Tournament, Player, Stage, MatchResult, get_available_ranking_criteria
from pmc.models import Playgroup, EventFormat


class TournamentForm(forms.ModelForm):
    # Main Stage fields
    main_pairing_strategy = forms.ChoiceField(
        choices=[],  # Will be populated in __init__
        initial='swiss',
        label='Main Stage Pairing Strategy'
    )
    main_max_players = forms.IntegerField(
        required=False,
        label='Main Stage Max Players',
        help_text='Leave empty for no limit'
    )
    main_allow_ties = forms.BooleanField(
        required=False,
        initial=False,
        label='Allow Ties in Main Stage'
    )
    main_score_reporting = forms.ChoiceField(
        choices=Stage.SCORE_REPORTING_CHOICES,
        initial=Stage.SCORE_REPORTING_OPTIONAL,
        label='Score Reporting in Main Stage'
    )

    # Playoff Stage fields
    enable_playoffs = forms.BooleanField(
        required=False,
        initial=False,
        label='Enable Playoff Stage'
    )
    playoff_max_players = forms.IntegerField(
        required=False,
        initial=8,
        label='Playoff Stage Max Players',
        help_text='Number of players advancing to playoffs'
    )
    playoff_score_reporting = forms.ChoiceField(
        choices=Stage.SCORE_REPORTING_CHOICES,
        initial=Stage.SCORE_REPORTING_DISABLED,
        label='Score Reporting in Playoffs',
        help_text='Ties are never allowed in playoffs'
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance')
        is_edit_mode = kwargs.pop('is_edit_mode', False)
        super().__init__(*args, **kwargs)

        # Populate pairing strategy choices dynamically
        from .pairing_strategies import get_strategy_choices
        self.fields['main_pairing_strategy'].choices = get_strategy_choices()

        # Disable is_closed field for create/copy operations
        if not is_edit_mode:
            self.fields['is_closed'].disabled = True
            self.fields['is_closed'].help_text = 'Tournament can only be closed after creation'

        # If editing existing tournament, populate stage fields
        if instance and instance.pk:
            main_stage = instance.stages.filter(order=1).first()
            if main_stage:
                self.fields['main_pairing_strategy'].initial = main_stage.pairing_strategy
                self.fields['main_max_players'].initial = main_stage.max_players
                self.fields['main_allow_ties'].initial = main_stage.are_ties_allowed
                self.fields['main_score_reporting'].initial = main_stage.report_full_scores

            playoff_stage = instance.stages.filter(order=2).first()
            if playoff_stage:
                self.fields['enable_playoffs'].initial = True
                self.fields['playoff_max_players'].initial = playoff_stage.max_players
                self.fields['playoff_score_reporting'].initial = playoff_stage.report_full_scores

    class Meta:
        model = Tournament
        fields = ['name', 'description',
                  'is_accepting_registrations', 'is_closed']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'style': 'text-wrap: auto'}),
        }

    def get_ranking_criteria_from_post(self, post_data):
        """Extract and validate ranking criteria from POST data"""
        criteria = []
        available_keys = [c.get_key()
                          for c in get_available_ranking_criteria()]

        # Extract criteria data from POST
        for key in available_keys:
            enabled = post_data.get(f'criterion_{key}_enabled') == 'on'
            order = post_data.get(f'criterion_{key}_order', '')

            if enabled:
                try:
                    order_int = int(order) if order else 1
                except (ValueError, TypeError):
                    order_int = 1

                criteria.append({
                    'key': key,
                    'enabled': True,
                    'order': order_int
                })
            else:
                criteria.append({
                    'key': key,
                    'enabled': False,
                    'order': 999  # High number for disabled criteria
                })

        # Sort enabled criteria by order and reassign sequential order numbers
        enabled_criteria = [c for c in criteria if c['enabled']]
        enabled_criteria.sort(key=lambda x: x['order'])

        # Reassign sequential order numbers to enabled criteria
        for i, criterion in enumerate(enabled_criteria):
            # Find this criterion in the original list and update its order
            for orig_criterion in criteria:
                if orig_criterion['key'] == criterion['key'] and orig_criterion['enabled']:
                    orig_criterion['order'] = i + 1
                    break

        return criteria


class PlayerForm(forms.ModelForm):
    username = forms.CharField(
        max_length=150,
        required=False,
        help_text="Leave empty to create a guest player"
    )

    class Meta:
        model = Player
        fields = ['nickname']

    def clean(self):
        cleaned_data = super().clean()
        username = (cleaned_data.get('username', '') or '').strip()
        nickname = (cleaned_data.get('nickname', '') or '').strip()

        # If username is provided, validate it exists
        if username:
            try:
                user = User.objects.get(username=username)
                cleaned_data['user_obj'] = user
            except User.DoesNotExist:
                raise forms.ValidationError(
                    f'No user found with username: {username}')
        else:
            # For guest players, nickname is required
            if not nickname:
                raise forms.ValidationError(
                    'Nickname is required for guest players')
            cleaned_data['user_obj'] = None

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.user = self.cleaned_data.get('user_obj')
        if commit:
            instance.save()
        return instance


class StageForm(forms.ModelForm):
    pairing_strategy = forms.ChoiceField(
        choices=[])  # Will be populated in __init__

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate pairing strategy choices dynamically
        from .pairing_strategies import get_strategy_choices
        self.fields['pairing_strategy'].choices = get_strategy_choices()

    class Meta:
        model = Stage
        fields = ['name', 'description', 'pairing_strategy']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class MatchResultForm(forms.ModelForm):
    class Meta:
        model = MatchResult
        fields = ['winner', 'player_one_score', 'player_two_score']

    def clean_winner(self):
        winner_id = self.cleaned_data.get('winner')
        if winner_id:
            from .models import StagePlayer
            return StagePlayer.objects.get(id=winner_id)
        return None

    def clean_player_one_score(self):
        score = self.cleaned_data.get('player_one_score')
        if score == '' or score is None:
            return None
        return score

    def clean_player_two_score(self):
        score = self.cleaned_data.get('player_two_score')
        if score == '' or score is None:
            return None
        return score

    def clean(self):
        cleaned_data = super().clean()
        winner = cleaned_data.get('winner')
        player_one_score = cleaned_data.get('player_one_score')
        player_two_score = cleaned_data.get('player_two_score')

        if not hasattr(self, 'match') or not self.match:
            return cleaned_data

        stage = self.match.round.stage

        # Validate winner selection based on stage settings
        if not stage.are_ties_allowed and not winner:
            raise forms.ValidationError(
                "A winner must be selected - ties are not allowed in this stage.")

        # Validate scores based on stage settings
        if stage.report_full_scores == Stage.SCORE_REPORTING_REQUIRED:
            if player_one_score is None or player_two_score is None:
                raise forms.ValidationError(
                    "Scores are required for this stage.")

        return cleaned_data

    def __init__(self, *args, **kwargs):
        match = kwargs.pop('match', None)
        super().__init__(*args, **kwargs)

        # Store match for validation
        self.match = match

        if match:
            stage = match.round.stage

            # Build winner choices based on stage settings
            choices = []
            if stage.are_ties_allowed:
                choices.append(('', 'Tie'))

            if match.player_one:
                choices.append(
                    (match.player_one.id, match.player_one.player.get_display_name()))
            if match.player_two:
                choices.append(
                    (match.player_two.id, match.player_two.player.get_display_name()))

            self.fields['winner'] = forms.ChoiceField(
                choices=choices,
                required=True if not stage.are_ties_allowed else False,
                widget=forms.Select(attrs={'class': 'form-select'})
            )

            # Configure score fields based on stage settings
            if stage.report_full_scores == Stage.SCORE_REPORTING_DISABLED:
                # Remove score fields entirely
                del self.fields['player_one_score']
                del self.fields['player_two_score']
            elif stage.report_full_scores == Stage.SCORE_REPORTING_REQUIRED:
                # Make score fields required
                self.fields['player_one_score'].required = True
                self.fields['player_two_score'].required = True


class PlayerRegistrationForm(forms.Form):
    nickname = forms.CharField(max_length=100, required=False)


class AddMatchForm(forms.Form):
    player_one = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Player One'
    )
    player_two = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Player Two',
        required=False
    )

    def __init__(self, *args, **kwargs):
        available_players = kwargs.pop('available_players', [])
        super().__init__(*args, **kwargs)

        choices = [('', 'Select a player...')]
        for stage_player in available_players:
            choices.append(
                (stage_player.id, stage_player.player.get_display_name()))

        self.fields['player_one'].choices = choices
        player_two_choices = [
            ('', 'Select a player or leave empty for bye...')]
        for stage_player in available_players:
            player_two_choices.append(
                (stage_player.id, stage_player.player.get_display_name()))
        self.fields['player_two'].choices = player_two_choices

    def clean(self):
        cleaned_data = super().clean()
        player_one_id = cleaned_data.get('player_one')
        player_two_id = cleaned_data.get('player_two')

        if not player_one_id:
            raise forms.ValidationError('Player One is required.')

        if player_one_id and player_two_id:
            if player_one_id == player_two_id:
                raise forms.ValidationError(
                    'Please select two different players.')

        return cleaned_data

    def get_selected_players(self):
        from .models import StagePlayer
        player_one_id = self.cleaned_data.get('player_one')
        player_two_id = self.cleaned_data.get('player_two')

        player_one = StagePlayer.objects.get(
            id=player_one_id) if player_one_id else None
        player_two = StagePlayer.objects.get(
            id=player_two_id) if player_two_id else None

        return player_one, player_two


class SelectPlaygroupForm(forms.Form):
    playgroup = forms.ModelChoiceField(
        queryset=Playgroup.objects.none(),
        empty_label='Select a playgroup...',
        required=True,
        label='Playgroup'
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            self.fields['playgroup'].queryset = Playgroup.objects.filter(
                members__user=user,
                members__is_staff=True
            ).distinct()


class TournamentExportForm(forms.Form):
    name = forms.CharField(
        max_length=200,
        required=True,
        label='Event Name'
    )
    start_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Event Date'
    )
    is_casual = forms.ChoiceField(
        choices=[(False, 'Tournament'), (True, 'Open Play')],
        required=True,
        initial=False,
        label='Event Type'
    )
    format = forms.ModelChoiceField(
        queryset=EventFormat.objects.all(),
        empty_label='Other',
        required=False,
        label='Format'
    )

    def __init__(self, *args, **kwargs):
        tournament = kwargs.pop('tournament', None)
        super().__init__(*args, **kwargs)

        if tournament:
            self.fields['name'].initial = tournament.name
