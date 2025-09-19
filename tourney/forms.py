from django import forms
from django.contrib.auth.models import User
from .models import Tournament, Player, Stage, MatchResult, get_available_ranking_criteria
import json


class TournamentForm(forms.ModelForm):
    # Main Stage fields
    main_pairing_strategy = forms.ChoiceField(
        choices=[
            ('swiss', 'Swiss'),
            ('single_elimination', 'Single Elimination'),
            ('round_robin', 'Round Robin (Self Scheduled)'),
        ],
        initial='swiss',
        label='Main Stage Pairing Strategy'
    )
    main_max_players = forms.IntegerField(
        required=False,
        label='Main Stage Max Players',
        help_text='Leave empty for no limit'
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

    # Ranking Criteria fields - these will be processed from POST data
    # No form field needed since we'll handle criteria directly in the view

    class Meta:
        model = Tournament
        fields = ['name', 'description', 'is_accepting_registrations']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance')
        super().__init__(*args, **kwargs)

        # If editing existing tournament, populate stage fields
        if instance and instance.pk:
            main_stage = instance.stages.filter(order=1).first()
            if main_stage:
                self.fields['main_pairing_strategy'].initial = main_stage.pairing_strategy
                self.fields['main_max_players'].initial = main_stage.max_players

            playoff_stage = instance.stages.filter(order=2).first()
            if playoff_stage:
                self.fields['enable_playoffs'].initial = True
                self.fields['playoff_max_players'].initial = playoff_stage.max_players

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
    PAIRING_STRATEGY_CHOICES = [
        ('swiss', 'Swiss'),
        ('single_elimination', 'Single Elimination'),
        ('round_robin', 'Round Robin (Self Scheduled)'),
    ]

    pairing_strategy = forms.ChoiceField(choices=PAIRING_STRATEGY_CHOICES)

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

    def clean(self):
        cleaned_data = super().clean()
        winner = cleaned_data.get('winner')
        player_one_score = cleaned_data.get('player_one_score')
        player_two_score = cleaned_data.get('player_two_score')

        # If scores are provided, validate they make sense with the winner
        if player_one_score is not None and player_two_score is not None:
            # Both scores provided - validate against winner
            if winner and hasattr(self, 'match'):
                match = getattr(self, 'match', None)
                if match:
                    if winner == match.player_one and player_one_score <= player_two_score:
                        raise forms.ValidationError(
                            "Player one is selected as winner but has a lower or equal score."
                        )
                    elif winner == match.player_two and player_two_score <= player_one_score:
                        raise forms.ValidationError(
                            "Player two is selected as winner but has a lower or equal score."
                        )
            elif not winner and player_one_score != player_two_score:
                raise forms.ValidationError(
                    "Scores indicate a clear winner, but 'Tie' is selected. Please select the appropriate winner or adjust scores."
                )
        elif (player_one_score is not None) != (player_two_score is not None):
            # Only one score provided
            raise forms.ValidationError(
                "Please provide both player scores or leave both blank."
            )

        return cleaned_data

    def __init__(self, *args, **kwargs):
        match = kwargs.pop('match', None)
        super().__init__(*args, **kwargs)

        # Store match for validation
        self.match = match

        if match:
            choices = [('', 'Tie')]
            if match.player_one:
                choices.append(
                    (match.player_one.id, match.player_one.player.get_display_name()))
            if match.player_two:
                choices.append(
                    (match.player_two.id, match.player_two.player.get_display_name()))

            self.fields['winner'] = forms.ChoiceField(
                choices=choices,
                required=False,
                widget=forms.Select(attrs={'class': 'form-select'})
            )


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
        label='Player Two'
    )

    def __init__(self, *args, **kwargs):
        available_players = kwargs.pop('available_players', [])
        super().__init__(*args, **kwargs)

        choices = [('', 'Select a player...')]
        for stage_player in available_players:
            choices.append((stage_player.id, stage_player.player.get_display_name()))

        self.fields['player_one'].choices = choices
        self.fields['player_two'].choices = choices

    def clean(self):
        cleaned_data = super().clean()
        player_one_id = cleaned_data.get('player_one')
        player_two_id = cleaned_data.get('player_two')

        if player_one_id and player_two_id:
            if player_one_id == player_two_id:
                raise forms.ValidationError('Please select two different players.')

        return cleaned_data

    def get_selected_players(self):
        from .models import StagePlayer
        player_one_id = self.cleaned_data.get('player_one')
        player_two_id = self.cleaned_data.get('player_two')

        player_one = StagePlayer.objects.get(id=player_one_id) if player_one_id else None
        player_two = StagePlayer.objects.get(id=player_two_id) if player_two_id else None

        return player_one, player_two
