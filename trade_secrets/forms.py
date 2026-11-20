import re
import uuid
from dataclasses import replace

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from requests import RequestException

from decks.models import Deck, House, Set
from lineups.models import Lineup, LineupVersion

from . import engine
from .engine import Action, AdaptiveReport, GameType, PlayedDeckRule, Seat, StepSpec

DECK_LINK_SEPARATORS = re.compile(r'[\s,;]+')
HYDRATION_FAILURES = (
    ValueError, KeyError, IndexError, RequestException, Set.DoesNotExist, House.DoesNotExist)
BUILDER_ACTION_PATTERN = re.compile(r'^(add|up|down|remove):(\w+)$')
DEFAULT_SUBMIT_QUANTITY = 3
DIFFERENT_DECKS_CHOSEN = 'different'


def parse_deck_links(text):
    deck_ids = []
    unrecognized = []
    for token in DECK_LINK_SEPARATORS.split(text.strip()):
        if not token:
            continue
        deck_id = Deck.get_id_from_master_vault_url(token)
        if deck_id is None:
            unrecognized.append(token)
        else:
            deck_ids.append(uuid.UUID(deck_id))
    return deck_ids, unrecognized


def ensure_decks_hydrated(deck_ids):
    known_decks = Deck.objects.in_bulk(deck_ids)
    failed_ids = []
    for deck_id in deck_ids:
        deck = known_decks.get(deck_id)
        if deck is not None and deck.name:
            continue
        deck = deck or Deck(id=deck_id)
        try:
            deck.hydrate_from_master_vault(save=True)
        except HYDRATION_FAILURES:
            failed_ids.append(deck_id)
    return failed_ids


def validate_deck_selection(deck_ids, required_count):
    if len(set(deck_ids)) != len(deck_ids):
        raise ValidationError(_('Each deck can only be submitted once.'))
    if len(deck_ids) != required_count:
        raise ValidationError(_('This format needs exactly {required} decks; you provided {provided}.').format(
            required=required_count, provided=len(deck_ids)))
    failed_ids = ensure_decks_hydrated(deck_ids)
    if failed_ids:
        raise ValidationError(
            _('Could not fetch these decks from Master Vault: {links}').format(
                links=', '.join(Deck.get_master_vault_ui_url_from_id(deck_id) for deck_id in failed_ids)))


class DeckLinksForm(forms.Form):
    deck_links = forms.CharField(
        label=_('Deck links'),
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': _('Master Vault or Decks of KeyForge links, one per line'),
            'autocomplete': 'off',
            'spellcheck': 'false',
        }))

    def __init__(self, *args, required_count, **kwargs):
        super().__init__(*args, **kwargs)
        self.required_count = required_count
        self.deck_ids = []

    def clean_deck_links(self):
        deck_ids, unrecognized = parse_deck_links(self.cleaned_data['deck_links'])
        if unrecognized:
            raise ValidationError(
                _('No deck found in: {tokens}').format(tokens=', '.join(unrecognized)))
        validate_deck_selection(deck_ids, self.required_count)
        self.deck_ids = deck_ids
        return self.cleaned_data['deck_links']


class DeckLineupForm(forms.Form):
    lineup = forms.ModelChoiceField(queryset=Lineup.objects.none(), label=_('Lineup'))
    version = forms.ModelChoiceField(
        queryset=LineupVersion.objects.none(), label=_('Version'), required=False)

    def __init__(self, *args, user, required_count, **kwargs):
        super().__init__(*args, **kwargs)
        self.required_count = required_count
        self.deck_ids = []
        self.source_version = None
        self.fields['lineup'].queryset = Lineup.objects.filter(owner=user)
        self.fields['version'].queryset = LineupVersion.objects.filter(lineup__owner=user)

    def clean(self):
        cleaned_data = super().clean()
        lineup = cleaned_data.get('lineup')
        if lineup is None:
            return cleaned_data
        version = cleaned_data.get('version') or lineup.latest_version
        if version is None or version.lineup_id != lineup.id:
            raise ValidationError(_('Choose a version of this lineup.'))
        deck_ids = [version_deck.deck_id for version_deck in version.version_decks.all()]
        validate_deck_selection(deck_ids, self.required_count)
        self.deck_ids = deck_ids
        self.source_version = version
        return cleaned_data


class PickForm(forms.Form):
    step_order = forms.IntegerField(widget=forms.HiddenInput)
    deck = forms.TypedMultipleChoiceField(coerce=int, required=False)

    def __init__(self, *args, choice_ids, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deck'].choices = [(deck_id, deck_id) for deck_id in choice_ids]


class PlayResultForm(forms.Form):
    winner_seat = forms.ChoiceField(label=_('Who won?'))
    host_score = forms.IntegerField(min_value=0, required=False)
    guest_score = forms.IntegerField(min_value=0, required=False)

    def __init__(self, *args, seat_names, adaptive_deck_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.seat_names = seat_names
        self.fields['winner_seat'].choices = [(seat, seat_names[seat]) for seat in engine.SEATS]
        self.is_adaptive = bool(adaptive_deck_choices)
        if self.is_adaptive:
            self.add_adaptive_fields([(str(deck_id), name) for deck_id, name in adaptive_deck_choices])

    def add_adaptive_fields(self, deck_choices):
        self.fields['contested_deck'] = forms.ChoiceField(
            label=_('Which deck was bid on?'),
            choices=deck_choices + [(DIFFERENT_DECKS_CHOSEN, _('We chose different decks'))])
        self.fields['chain_bid'] = forms.IntegerField(
            label=_('Final bid'), min_value=engine.OPENING_CHAIN_BID, max_value=engine.MAXIMUM_CHAIN_BID,
            required=False)
        self.fields['host_played_deck'] = forms.ChoiceField(
            label=_('Which deck did {name} play?').format(name=self.seat_names[Seat.HOST]),
            choices=deck_choices)
        self.fields['first_deck'] = forms.ChoiceField(
            label=_('Which deck went first?'),
            choices=[('', _('Not recorded'))] + deck_choices, required=False)

    def clean(self):
        cleaned_data = super().clean()
        if (cleaned_data.get('host_score') is None) != (cleaned_data.get('guest_score') is None):
            raise ValidationError(_('Enter a score for both players, or leave both blank.'))
        if self.is_adaptive and cleaned_data.get('contested_deck') == DIFFERENT_DECKS_CHOSEN:
            cleaned_data['chain_bid'] = None
        elif self.is_adaptive and cleaned_data.get('contested_deck') and cleaned_data.get('chain_bid') is None:
            self.add_error('chain_bid', _('Enter the final chain bid.'))
        return cleaned_data

    def adaptive_report(self):
        if not self.is_adaptive:
            return None
        contested_deck = self.cleaned_data['contested_deck']
        return AdaptiveReport(
            host_played_deck_id=int(self.cleaned_data['host_played_deck']),
            contested_deck_id=None if contested_deck == DIFFERENT_DECKS_CHOSEN else int(contested_deck),
            chain_bid=self.cleaned_data['chain_bid'],
            first_deck_id=int(self.cleaned_data['first_deck']) if self.cleaned_data['first_deck'] else None,
        )

    def player_slots(self):
        selected_seat = self['winner_seat'].value()
        return [
            {
                'seat': seat,
                'name': self.seat_names[seat],
                'is_winner': selected_seat == seat,
                'score_field': self[f'{seat}_score'],
            }
            for seat in engine.SEATS
        ]


def adaptive_result_initial(plan):
    initial = {'first_deck': plan.first_deck_id or ''}
    if plan.contested_deck_id is not None:
        initial['contested_deck'] = str(plan.contested_deck_id)
    elif plan.is_assigned:
        initial['contested_deck'] = DIFFERENT_DECKS_CHOSEN
    if plan.is_assigned:
        initial['host_played_deck'] = str(plan.played_by_seat[Seat.HOST])
        initial['chain_bid'] = plan.chains
    return initial


class ChainBidForm(forms.Form):
    chains = forms.IntegerField(min_value=engine.OPENING_CHAIN_BID, max_value=engine.MAXIMUM_CHAIN_BID)


class TemplateDetailsForm(forms.Form):
    name = forms.CharField(max_length=100, label=_('Name'))
    description = forms.CharField(
        required=False, label=_('Description'), widget=forms.Textarea(attrs={'rows': 2}))


def default_builder_steps():
    return [
        StepSpec(0, Action.SUBMIT, DEFAULT_SUBMIT_QUANTITY),
        StepSpec(1, Action.BAN, 1),
        StepSpec(2, Action.PLAY, 1, PlayedDeckRule.INELIGIBLE),
    ]


def parse_positive_integer(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def parse_builder_steps(data):
    steps = []
    index = 0
    while f'steps-{index}-action' in data:
        action = data.get(f'steps-{index}-action')
        if action in Action.values:
            quantity = 1 if action in (Action.PLAY, Action.BAN_MATCHUP) else parse_positive_integer(
                data.get(f'steps-{index}-quantity'), 1)
            rule = data.get(f'steps-{index}-rule', PlayedDeckRule.INELIGIBLE)
            if rule not in PlayedDeckRule.values:
                rule = PlayedDeckRule.INELIGIBLE
            game_type = data.get(f'steps-{index}-type', GameType.ARCHON)
            if game_type not in GameType.values or action != Action.PLAY:
                game_type = GameType.ARCHON
            steps.append(StepSpec(len(steps), action, quantity, rule, game_type))
        index += 1
    if not steps or not steps[0].is_submit:
        steps.insert(0, StepSpec(0, Action.SUBMIT, DEFAULT_SUBMIT_QUANTITY))
    return renumber(steps)


def renumber(steps):
    return [replace(step, order=order) for order, step in enumerate(steps)]


def apply_builder_action(steps, builder_action):
    match = BUILDER_ACTION_PATTERN.match(builder_action or '')
    if not match:
        return steps
    verb, argument = match.groups()
    steps = list(steps)
    if verb == 'add' and argument in Action.values and argument != Action.SUBMIT:
        if len(steps) < engine.MAXIMUM_STEPS_PER_TEMPLATE:
            steps.append(StepSpec(len(steps), argument, 1))
        return renumber(steps)
    if not argument.isdigit():
        return steps
    index = int(argument)
    if index < 1 or index >= len(steps):
        return steps
    if verb == 'remove':
        del steps[index]
    elif verb == 'up' and index > 1:
        steps[index - 1], steps[index] = steps[index], steps[index - 1]
    elif verb == 'down' and index < len(steps) - 1:
        steps[index], steps[index + 1] = steps[index + 1], steps[index]
    return renumber(steps)
