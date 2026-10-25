from dataclasses import dataclass, field

from django.db.models import TextChoices
from django.utils.translation import gettext_lazy as _


MAXIMUM_STEPS_PER_TEMPLATE = 20
MAXIMUM_DECKS_PER_PLAYER = 12
MAXIMUM_STEP_QUANTITY = 12
MINIMUM_MATCHUPS_FOR_BAN = 3
MATCHUPS_REMOVED_BY_SEPARATE_BANS = 2


class Action(TextChoices):
    SUBMIT = 'submit', _('Submit decks')
    BAN = 'ban', _('Ban')
    SAFE = 'safe', _('Safe')
    STEAL = 'steal', _('Steal')
    PLAY = 'play', _('Play')
    BAN_MATCHUP = 'ban_matchup', _('Ban matchup')


class PlayedDeckRule(TextChoices):
    ELIGIBLE = 'eligible', _('Yes')
    INELIGIBLE = 'ineligible', _('No')
    LOSING_ONLY = 'losing_only', _('Only losing decks')


class Seat(TextChoices):
    HOST = 'host', _('Host')
    GUEST = 'guest', _('Guest')


class DeckStatus(TextChoices):
    AVAILABLE = 'available', _('Available')
    BANNED = 'banned', _('Banned')
    SAFED = 'safed', _('Safe')
    STOLEN = 'stolen', _('Stolen')
    PLAYED = 'played', _('Played')
    INELIGIBLE = 'ineligible', _('Out')


class Phase(TextChoices):
    WAITING_FOR_GUEST = 'waiting_for_guest', _('Waiting for opponent')
    SUBMITTING_DECKS = 'submitting_decks', _('Submitting decks')
    SELECTING = 'selecting', _('Selecting')
    AWAITING_RESULT = 'awaiting_result', _('Awaiting result')
    CONCLUDED = 'concluded', _('Concluded')
    COMPLETE = 'complete', _('Complete')


SEATS = (Seat.HOST, Seat.GUEST)
FINISHED_PHASES = (Phase.CONCLUDED, Phase.COMPLETE)


def opponent_of(seat):
    return Seat.GUEST if seat == Seat.HOST else Seat.HOST


@dataclass(frozen=True)
class StepSpec:
    order: int
    action: str
    quantity: int = 1
    played_deck_rule: str = PlayedDeckRule.INELIGIBLE

    @property
    def is_play(self):
        return self.action == Action.PLAY

    @property
    def is_submit(self):
        return self.action == Action.SUBMIT

    @property
    def is_matchup_ban(self):
        return self.action == Action.BAN_MATCHUP


@dataclass(frozen=True)
class PoolDeck:
    id: int
    seat: str


@dataclass
class DeckState:
    id: int
    original_seat: str
    holder_seat: str
    is_banned: bool = False
    is_safed: bool = False
    is_spent: bool = False
    spent_by_winning: bool = False
    spent_at_order: int = None
    stolen_at_orders: list = field(default_factory=list)
    played_at_orders: list = field(default_factory=list)

    @property
    def is_open(self):
        return not (self.is_banned or self.is_safed or self.is_spent)

    @property
    def is_playable(self):
        return not (self.is_banned or self.is_spent)

    @property
    def is_held_by_opponent_of_owner(self):
        return self.holder_seat != self.original_seat


@dataclass
class RevealedStep:
    step: StepSpec
    picks_by_seat: dict


@dataclass
class GameState:
    steps: tuple
    decks: dict
    revealed_count: int
    winners: dict
    history: list
    banned_matchup_orders: set = field(default_factory=set)

    @property
    def current_step(self):
        if self.revealed_count < len(self.steps):
            return self.steps[self.revealed_count]
        return None

    def decks_held_by(self, seat):
        return [deck for deck in self.decks.values() if deck.holder_seat == seat]

    def decks_submitted_by(self, seat):
        return [deck for deck in self.decks.values() if deck.original_seat == seat]


@dataclass(frozen=True)
class StepTrace:
    order: int
    fewest_open: int
    most_open: int
    fewest_safed: int
    most_safed: int
    fewest_matchups: int = 0
    error: str = ''

    @property
    def open_range_varies(self):
        return self.fewest_open != self.most_open

    @property
    def safed_range_varies(self):
        return self.fewest_safed != self.most_safed

    @property
    def has_matchups(self):
        return self.fewest_matchups > 0


@dataclass
class PoolEstimate:
    open: int
    safed: int = 0

    @property
    def total(self):
        return self.open + self.safed

    def remove_open(self, quantity):
        usable = min(quantity, self.open)
        self.open -= usable
        return usable

    def protect_open(self, quantity):
        self.safed += self.remove_open(quantity)

    def consume_one(self):
        if self.safed:
            self.safed -= 1
        elif self.open:
            self.open -= 1


def game_number_for_order(steps, order):
    return sum(1 for step in steps if step.is_play and step.order <= order)


def play_steps(steps):
    return [step for step in steps if step.is_play]


def is_matchup(steps, step):
    return step.is_play and any(other.is_matchup_ban and other.order > step.order for other in steps)


def is_awaiting_matchup_ban(steps, step, revealed_count):
    return any(
        other.is_matchup_ban and other.order > step.order and other.order >= revealed_count
        for other in steps)


def is_result_locked(steps, order, result_orders):
    is_matchup_result = is_matchup(steps, steps[order])
    return any(
        other > order and is_matchup(steps, steps[other]) == is_matchup_result
        for other in result_orders)


def game_label(steps, step):
    number = game_number_for_order(steps, step.order)
    if is_matchup(steps, step):
        return str(_('Matchup {number}').format(number=number))
    return str(_('Game {number}').format(number=number))


def replay(steps, pool_decks, revealed_count, revealed_picks, winners):
    state = GameState(
        steps=tuple(steps),
        decks={
            pool_deck.id: DeckState(
                id=pool_deck.id,
                original_seat=pool_deck.seat,
                holder_seat=pool_deck.seat)
            for pool_deck in pool_decks
        },
        revealed_count=0,
        winners=dict(winners),
        history=[],
    )
    for step in state.steps[:revealed_count]:
        resolve_step(state, step, revealed_picks.get(step.order, {}))
    return state


def resolve_step(state, step, picks_by_seat):
    normalized_picks = {
        seat: tuple(picks_by_seat.get(seat, ())) for seat in SEATS}
    if step.action == Action.BAN:
        for deck_id in all_picked_ids(normalized_picks):
            state.decks[deck_id].is_banned = True
    elif step.action == Action.SAFE:
        for deck_id in all_picked_ids(normalized_picks):
            state.decks[deck_id].is_safed = True
    elif step.action == Action.STEAL:
        for seat, deck_ids in normalized_picks.items():
            for deck_id in deck_ids:
                state.decks[deck_id].holder_seat = seat
                state.decks[deck_id].stolen_at_orders.append(step.order)
    elif step.action == Action.PLAY:
        for seat, deck_ids in normalized_picks.items():
            for deck_id in deck_ids:
                record_play(state, step, seat, state.decks[deck_id])
    elif step.action == Action.BAN_MATCHUP:
        state.banned_matchup_orders.update(all_picked_ids(normalized_picks))
    state.history.append(RevealedStep(step=step, picks_by_seat=normalized_picks))
    state.revealed_count += 1


def all_picked_ids(picks_by_seat):
    return [deck_id for deck_ids in picks_by_seat.values() for deck_id in deck_ids]


def record_play(state, step, seat, deck):
    deck.played_at_orders.append(step.order)
    if step.played_deck_rule == PlayedDeckRule.INELIGIBLE:
        deck.is_spent = True
        deck.spent_at_order = step.order
    elif step.played_deck_rule == PlayedDeckRule.LOSING_ONLY and state.winners.get(step.order) == seat:
        deck.is_spent = True
        deck.spent_by_winning = True
        deck.spent_at_order = step.order


def choices_for(state, step, seat):
    if step.action in (Action.BAN, Action.STEAL):
        return [deck.id for deck in state.decks_held_by(opponent_of(seat)) if deck.is_open]
    if step.action == Action.SAFE:
        return [deck.id for deck in state.decks_held_by(seat) if deck.is_open]
    if step.action == Action.PLAY:
        return [deck.id for deck in state.decks_held_by(seat) if deck.is_playable]
    if step.action == Action.BAN_MATCHUP:
        return unbanned_matchup_orders(state)
    return []


def unbanned_matchup_orders(state):
    return [
        revealed.step.order for revealed in state.history
        if revealed.step.is_play and revealed.step.order not in state.banned_matchup_orders
    ]


def required_pick_count(state, step, seat):
    if step.is_submit:
        return step.quantity
    return min(step.quantity, len(choices_for(state, step, seat)))


def seats_needing_picks(state, step):
    return [seat for seat in SEATS if required_pick_count(state, step, seat) > 0]


def validate_picks(state, step, seat, deck_ids):
    errors = []
    deck_ids = list(deck_ids)
    expected_count = required_pick_count(state, step, seat)
    noun = _('matchup') if step.is_matchup_ban else _('deck')
    if len(set(deck_ids)) != len(deck_ids):
        errors.append(str(_('Each {noun} can only be picked once.').format(noun=noun)))
    if len(set(deck_ids)) != expected_count:
        errors.append(str(_('Pick exactly {count} {noun}(s).').format(count=expected_count, noun=noun)))
    eligible_ids = set(choices_for(state, step, seat))
    if any(deck_id not in eligible_ids for deck_id in deck_ids):
        errors.append(str(_('That {noun} cannot be picked for this step.').format(noun=noun)))
    return errors


def missing_result_step(state):
    if state.current_step is None:
        return None
    for revealed in state.history:
        step = revealed.step
        if step.is_play and step.played_deck_rule == PlayedDeckRule.LOSING_ONLY and step.order not in state.winners:
            return step
    return None


def phase(state, has_guest):
    if not has_guest:
        return Phase.WAITING_FOR_GUEST
    step = state.current_step
    if step is None:
        return Phase.COMPLETE
    if step.is_submit:
        return Phase.SUBMITTING_DECKS
    if missing_result_step(state) is not None:
        return Phase.AWAITING_RESULT
    if step.is_play and len(seats_needing_picks(state, step)) < len(SEATS):
        return Phase.CONCLUDED
    return Phase.SELECTING


def deck_status(deck):
    if deck.is_banned:
        return DeckStatus.BANNED
    if deck.is_spent:
        return DeckStatus.INELIGIBLE
    if deck.is_safed:
        return DeckStatus.SAFED
    if deck.is_held_by_opponent_of_owner:
        return DeckStatus.STOLEN
    if deck.played_at_orders:
        return DeckStatus.PLAYED
    return DeckStatus.AVAILABLE


def ineligible_reason(state, deck):
    if not deck.is_spent:
        return ''
    game = game_label(state.steps, state.steps[deck.spent_at_order]).lower()
    if deck.spent_by_winning:
        return str(_('Won {game}').format(game=game))
    return str(_('Played in {game}').format(game=game))


def step_label(step):
    if step.is_play or step.is_matchup_ban:
        return str(Action(step.action).label)
    return f'{Action(step.action).label} {step.quantity}'


def simulate_template_steps(steps):
    if not steps or not steps[0].is_submit:
        return []
    cautious = PoolEstimate(open=steps[0].quantity)
    hopeful = PoolEstimate(open=steps[0].quantity)
    fewest_matchups = 0
    traces = [trace_for(steps[0], cautious, hopeful, fewest_matchups)]
    for display_number, step in enumerate(steps[1:], start=2):
        if step.is_matchup_ban:
            error = matchup_ban_error(display_number, steps, step, fewest_matchups)
            fewest_matchups = max(0, fewest_matchups - MATCHUPS_REMOVED_BY_SEPARATE_BANS)
        else:
            error = shortage_error(display_number, step, cautious, hopeful)
            apply_step_to_estimates(step, cautious, hopeful)
            fewest_matchups += 1 if step.is_play else 0
        traces.append(trace_for(step, cautious, hopeful, fewest_matchups, error))
    return traces


def trace_for(step, cautious, hopeful, fewest_matchups, error=''):
    return StepTrace(
        step.order, cautious.open, hopeful.open, cautious.safed, hopeful.safed, fewest_matchups, error)


def matchup_ban_error(display_number, steps, step, fewest_matchups):
    if any(other.is_play and other.order < step.order and other.played_deck_rule == PlayedDeckRule.LOSING_ONLY
           for other in steps):
        return str(_(
            'Step {number} (Ban matchup): matchups can\'t be banned after a Play step that uses '
            '"Only losing decks", because those games must be played before the match can continue.'
        ).format(number=display_number))
    if fewest_matchups < MINIMUM_MATCHUPS_FOR_BAN:
        return str(_(
            'Step {number} (Ban matchup): needs at least {needed} unbanned matchups but as few as '
            '{available} may remain.'
        ).format(number=display_number, needed=MINIMUM_MATCHUPS_FOR_BAN, available=fewest_matchups))
    return ''


def shortage_error(display_number, step, cautious, hopeful):
    if step.is_play:
        if hopeful.total < 1:
            return shortage_message(display_number, step, 1, 'at most', 0)
        return ''
    if hopeful.open < step.quantity:
        return shortage_message(display_number, step, step.quantity, 'at most', hopeful.open)
    if cautious.open < step.quantity:
        return shortage_message(display_number, step, step.quantity, 'as few as', cautious.open)
    return ''


def apply_step_to_estimates(step, cautious, hopeful):
    for estimate in (cautious, hopeful):
        if step.action == Action.BAN:
            estimate.remove_open(step.quantity)
        elif step.action == Action.SAFE:
            estimate.protect_open(step.quantity)
    if step.is_play and step.played_deck_rule == PlayedDeckRule.INELIGIBLE:
        cautious.consume_one()
        hopeful.consume_one()
    elif step.is_play and step.played_deck_rule == PlayedDeckRule.LOSING_ONLY:
        cautious.consume_one()


def shortage_message(display_number, step, needed, bound, available):
    return str(_(
        'Step {number} ({label}): needs {needed} eligible deck(s) but {bound} {available} may remain.'
    ).format(number=display_number, label=step_label(step), needed=needed, bound=bound, available=available))


def validate_template_steps(steps):
    steps = list(steps)
    if not steps:
        return [str(_('A template needs at least one step.'))]
    errors = []
    if len(steps) > MAXIMUM_STEPS_PER_TEMPLATE:
        errors.append(str(_('A template can have at most {maximum} steps.').format(
            maximum=MAXIMUM_STEPS_PER_TEMPLATE)))
    if not steps[0].is_submit:
        errors.append(str(_('The first step must be Submit decks.')))
    for display_number, step in enumerate(steps, start=1):
        errors.extend(structural_errors_for_step(display_number, step))
    if errors:
        return errors
    return [trace.error for trace in simulate_template_steps(steps) if trace.error]


def structural_errors_for_step(display_number, step):
    errors = []
    if step.action not in Action.values:
        return [str(_('Step {number}: unknown action.').format(number=display_number))]
    if step.is_submit and display_number != 1:
        errors.append(str(_('Step {number}: only the first step can submit decks.').format(
            number=display_number)))
    maximum = MAXIMUM_DECKS_PER_PLAYER if step.is_submit else MAXIMUM_STEP_QUANTITY
    if step.is_play and step.quantity != 1:
        errors.append(str(_('Step {number}: a Play step is always a single game.').format(
            number=display_number)))
    elif step.is_matchup_ban and step.quantity != 1:
        errors.append(str(_('Step {number}: a Ban matchup step always bans one matchup.').format(
            number=display_number)))
    elif not 1 <= step.quantity <= maximum:
        errors.append(str(_('Step {number}: quantity must be between 1 and {maximum}.').format(
            number=display_number, maximum=maximum)))
    if step.is_play and step.played_deck_rule not in PlayedDeckRule.values:
        errors.append(str(_('Step {number}: unknown played deck rule.').format(number=display_number)))
    return errors


def games_won(state):
    tally = {seat: 0 for seat in SEATS}
    for step in play_steps(state.steps[:state.revealed_count]):
        if step.order in state.banned_matchup_orders:
            continue
        winner = state.winners.get(step.order)
        if winner in tally:
            tally[winner] += 1
    return tally


def results_summary_lines(state, format_name, session_code, seat_names, deck_names, scores, share_url):
    def names_for(deck_ids):
        return '; '.join(deck_names.get(deck_id, '?') for deck_id in deck_ids)

    lines = [
        f'Trade Secrets: {format_name} ({session_code})',
        f'{seat_names[Seat.HOST]} vs {seat_names[Seat.GUEST]}',
    ]
    past_tense = {
        Action.BAN: 'banned',
        Action.SAFE: 'safed',
        Action.STEAL: 'stole',
    }
    for revealed in state.history:
        step = revealed.step
        picks = revealed.picks_by_seat
        if step.is_submit:
            for seat in SEATS:
                lines.append(f'{seat_names[seat]} decks: {names_for(d.id for d in state.decks_submitted_by(seat))}')
        elif step.is_play:
            lines.append(play_summary_line(state, step, picks, seat_names, deck_names, scores))
        elif step.is_matchup_ban:
            fragments = [
                f'{seat_names[seat]} banned '
                + ('; '.join(game_label(state.steps, state.steps[order]) for order in picks[seat]) or 'nothing')
                for seat in SEATS
            ]
            lines.append(f'{Action(step.action).label}: ' + '; '.join(fragments))
        else:
            fragments = [
                f'{seat_names[seat]} {past_tense[step.action]} {names_for(picks[seat]) or "nothing"}'
                for seat in SEATS
            ]
            lines.append(f'{Action(step.action).label}: ' + '; '.join(fragments))
    if play_steps(state.steps):
        tally = games_won(state)
        lines.append('Games won: ' + ', '.join(f'{seat_names[seat]} {tally[seat]}' for seat in SEATS))
    lines.append(share_url)
    return lines


def score_line(seat_names, host_score, guest_score):
    if host_score is None or guest_score is None:
        return ''
    return f'{seat_names[Seat.HOST]} {host_score} – {guest_score} {seat_names[Seat.GUEST]}'


def play_summary_line(state, step, picks, seat_names, deck_names, scores):
    matchup = ' vs '.join(
        f'{deck_names.get(picks[seat][0], "?") if picks[seat] else "no deck"} ({seat_names[seat]})'
        for seat in SEATS)
    winner = state.winners.get(step.order)
    if step.order in state.banned_matchup_orders:
        outcome = 'banned'
    elif winner is None:
        outcome = 'result not recorded'
    else:
        outcome = f'{seat_names[winner]} won'
        line = score_line(seat_names, *scores.get(step.order, (None, None)))
        if line:
            outcome += f', {line}'
    return f'{game_label(state.steps, step)}: {matchup} - {outcome}'
