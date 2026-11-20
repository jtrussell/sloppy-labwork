from dataclasses import dataclass, field

from django.db.models import TextChoices
from django.utils.translation import gettext_lazy as _


MAXIMUM_STEPS_PER_TEMPLATE = 20
MAXIMUM_DECKS_PER_PLAYER = 12
MAXIMUM_STEP_QUANTITY = 12
MINIMUM_MATCHUPS_FOR_BAN = 3
MATCHUPS_REMOVED_BY_SEPARATE_BANS = 2
OPENING_CHAIN_BID = 0
MAXIMUM_CHAIN_BID = 99


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


class GameType(TextChoices):
    ARCHON = 'archon', _('Archon')
    REVERSAL = 'reversal', _('Reversal')
    ADAPTIVE = 'adaptive', _('Adaptive')


class AdaptiveStage(TextChoices):
    PREFERENCE = 'preference', _('Choosing decks')
    BIDDING = 'bidding', _('Bidding chains')
    SETTLED = 'settled', _('Settled')


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
    game_type: str = GameType.ARCHON

    @property
    def is_play(self):
        return self.action == Action.PLAY

    @property
    def is_adaptive_game(self):
        return self.is_play and self.game_type == GameType.ADAPTIVE

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
    banned_at_order: int = None
    safed_at_order: int = None
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
class ChainBidEntry:
    seat: str
    chains: int = None

    @property
    def is_pass(self):
        return self.chains is None


@dataclass
class AdaptiveRecord:
    first_deck_id: int = None
    preferences: dict = field(default_factory=dict)
    bids: list = field(default_factory=list)


@dataclass(frozen=True)
class AdaptiveReport:
    host_played_deck_id: int
    contested_deck_id: int = None
    chain_bid: int = None
    first_deck_id: int = None


@dataclass
class GamePlan:
    game_type: str
    brought_by_seat: dict
    played_by_seat: dict = field(default_factory=dict)
    stage: str = AdaptiveStage.SETTLED
    first_deck_id: int = None
    preferences: dict = field(default_factory=dict)
    contested_deck_id: int = None
    bids: list = field(default_factory=list)
    high_bid: int = OPENING_CHAIN_BID
    high_bidder: str = None
    seat_to_bid: str = None
    chains: int = None
    chained_seat: str = None

    @property
    def is_assigned(self):
        return bool(self.played_by_seat)

    @property
    def is_adaptive(self):
        return self.game_type == GameType.ADAPTIVE

    @property
    def minimum_raise(self):
        return self.high_bid + 1

    @property
    def can_raise(self):
        return self.high_bid < MAXIMUM_CHAIN_BID

    def seat_that_brought(self, deck_id):
        return next(seat for seat, brought_id in self.brought_by_seat.items() if brought_id == deck_id)

    def deck_other_than(self, deck_id):
        return next(brought_id for brought_id in self.brought_by_seat.values() if brought_id != deck_id)

    def chains_for(self, seat):
        return self.chains if seat == self.chained_seat else None


def plan_game(step, brought_by_seat, record=None, report=None):
    plan = GamePlan(game_type=step.game_type, brought_by_seat=dict(brought_by_seat))
    if step.game_type == GameType.REVERSAL:
        plan.played_by_seat = {seat: plan.brought_by_seat[opponent_of(seat)] for seat in SEATS}
    elif step.game_type == GameType.ADAPTIVE and report is not None:
        apply_adaptive_report(plan, report)
    elif step.game_type == GameType.ADAPTIVE:
        apply_adaptive_record(plan, record or AdaptiveRecord())
    else:
        plan.played_by_seat = dict(plan.brought_by_seat)
    return plan


def apply_adaptive_report(plan, report):
    plan.first_deck_id = report.first_deck_id
    plan.played_by_seat = {
        Seat.HOST: report.host_played_deck_id,
        Seat.GUEST: plan.deck_other_than(report.host_played_deck_id),
    }
    if report.contested_deck_id is not None:
        plan.contested_deck_id = report.contested_deck_id
        plan.chains = report.chain_bid
        plan.high_bid = report.chain_bid
        plan.chained_seat = next(
            seat for seat, deck_id in plan.played_by_seat.items() if deck_id == report.contested_deck_id)
        plan.high_bidder = plan.chained_seat


def apply_adaptive_record(plan, record):
    plan.first_deck_id = record.first_deck_id
    plan.preferences = dict(record.preferences)
    if not set(SEATS) <= set(record.preferences):
        plan.stage = AdaptiveStage.PREFERENCE
        return
    if record.preferences[Seat.HOST] != record.preferences[Seat.GUEST]:
        plan.played_by_seat = dict(record.preferences)
        return
    plan.contested_deck_id = record.preferences[Seat.HOST]
    plan.bids = list(record.bids)
    plan.high_bidder = plan.seat_that_brought(plan.contested_deck_id)
    for bid in record.bids:
        if bid.is_pass:
            settle_chain_bidding(plan)
            return
        plan.high_bid = bid.chains
        plan.high_bidder = bid.seat
    plan.stage = AdaptiveStage.BIDDING
    plan.seat_to_bid = opponent_of(plan.high_bidder)


def settle_chain_bidding(plan):
    plan.chains = plan.high_bid
    plan.chained_seat = plan.high_bidder
    plan.played_by_seat = {
        plan.high_bidder: plan.contested_deck_id,
        opponent_of(plan.high_bidder): plan.deck_other_than(plan.contested_deck_id),
    }


def validate_adaptive_preference(plan, deck_id):
    if not plan.is_adaptive or plan.stage != AdaptiveStage.PREFERENCE:
        return [str(_('Deck choices for this game were already revealed.'))]
    if deck_id not in plan.brought_by_seat.values():
        return [str(_('Choose one of the two decks brought to this game.'))]
    return []


def validate_chain_bid(plan, seat, chains):
    if not plan.is_adaptive or plan.stage != AdaptiveStage.BIDDING:
        return [str(_('Bidding is not open for this game.'))]
    if seat != plan.seat_to_bid:
        return [str(_('It is not your turn to bid.'))]
    if chains is not None and not plan.minimum_raise <= chains <= MAXIMUM_CHAIN_BID:
        return [str(_('Bid at least {minimum} chains, or pass.').format(minimum=plan.minimum_raise))]
    return []


def validate_adaptive_report(brought_deck_ids, report):
    errors = []
    brought_deck_ids = set(brought_deck_ids)
    if report.host_played_deck_id not in brought_deck_ids:
        errors.append(str(_('Choose which deck each player played.')))
    if report.contested_deck_id is not None and report.contested_deck_id not in brought_deck_ids:
        errors.append(str(_('Choose which deck was bid on.')))
    if report.first_deck_id is not None and report.first_deck_id not in brought_deck_ids:
        errors.append(str(_('Choose one of the two decks as the deck that went first.')))
    if report.contested_deck_id is None and report.chain_bid is not None:
        errors.append(str(_('A chain bid only applies when both players chose the same deck.')))
    if report.contested_deck_id is not None and (
            report.chain_bid is None or not OPENING_CHAIN_BID <= report.chain_bid <= MAXIMUM_CHAIN_BID):
        errors.append(str(_('Enter the final chain bid.')))
    return errors


def archon_plans(state):
    return {
        revealed.step.order: plan_game(
            revealed.step, {seat: deck_ids[0] for seat, deck_ids in revealed.picks_by_seat.items() if deck_ids})
        for revealed in state.history if revealed.step.is_play
    }


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
            state.decks[deck_id].banned_at_order = step.order
    elif step.action == Action.SAFE:
        for deck_id in all_picked_ids(normalized_picks):
            state.decks[deck_id].is_safed = True
            state.decks[deck_id].safed_at_order = step.order
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


WAVE_ACTIONS = (Action.BAN, Action.SAFE, Action.STEAL, Action.BAN_MATCHUP)
DECK_WAVE_VERBS = {
    Action.BAN: 'banned',
    Action.SAFE: 'safed',
    Action.STEAL: 'stolen',
}


def has_multiple_waves(steps, action):
    return sum(1 for step in steps if step.action == action) > 1


def wave_number(steps, step):
    return sum(1 for other in steps if other.action == step.action and other.order <= step.order)


def wave_suffix(steps, order):
    step = steps[order]
    if not has_multiple_waves(steps, step.action):
        return ''
    return str(wave_number(steps, step))


def step_label(steps, step):
    if step.is_play:
        return game_label(steps, step)
    if step.is_submit:
        return str(_('Submit {count}').format(count=step.quantity))
    label = str(Action(step.action).label)
    suffix = wave_suffix(steps, step.order)
    return f'{label} {suffix}' if suffix else label


def wave_detail(step):
    if step.action not in DECK_WAVE_VERBS or step.quantity < 2:
        return ''
    return str(_('{count} decks {verb}').format(count=step.quantity, verb=DECK_WAVE_VERBS[step.action]))


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
            error = shortage_error(display_number, steps, step, cautious, hopeful)
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
            'Step {number} ({label}): matchups can\'t be banned after a Play step that uses '
            '"Only losing decks", because those games must be played before the match can continue.'
        ).format(number=display_number, label=step_label(steps, step)))
    if fewest_matchups < MINIMUM_MATCHUPS_FOR_BAN:
        return str(_(
            'Step {number} ({label}): needs at least {needed} unbanned matchups but as few as '
            '{available} may remain.'
        ).format(number=display_number, label=step_label(steps, step), needed=MINIMUM_MATCHUPS_FOR_BAN,
                 available=fewest_matchups))
    return ''


def shortage_error(display_number, steps, step, cautious, hopeful):
    if step.is_play:
        if hopeful.total < 1:
            return shortage_message(display_number, steps, step, 1, 'at most', 0)
        return ''
    if hopeful.open < step.quantity:
        return shortage_message(display_number, steps, step, step.quantity, 'at most', hopeful.open)
    if cautious.open < step.quantity:
        return shortage_message(display_number, steps, step, step.quantity, 'as few as', cautious.open)
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


def shortage_message(display_number, steps, step, needed, bound, available):
    return str(_(
        'Step {number} ({label}): needs {needed} eligible deck(s) but {bound} {available} may remain.'
    ).format(number=display_number, label=step_label(steps, step), needed=needed, bound=bound,
             available=available))


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
    if step.is_play and step.game_type not in GameType.values:
        errors.append(str(_('Step {number}: unknown game type.').format(number=display_number)))
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


def results_summary_lines(
        state, format_name, session_code, seat_names, deck_names, scores, share_url, game_plans=None):
    game_plans = archon_plans(state) if game_plans is None else game_plans

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
            lines.append(play_summary_line(state, step, game_plans[step.order], seat_names, deck_names, scores))
        elif step.is_matchup_ban:
            fragments = [
                f'{seat_names[seat]} banned '
                + ('; '.join(game_label(state.steps, state.steps[order]) for order in picks[seat]) or 'nothing')
                for seat in SEATS
            ]
            lines.append(f'{summary_heading(state.steps, step)}: ' + '; '.join(fragments))
        else:
            fragments = [
                f'{seat_names[seat]} {past_tense[step.action]} {names_for(picks[seat]) or "nothing"}'
                for seat in SEATS
            ]
            lines.append(f'{summary_heading(state.steps, step)}: ' + '; '.join(fragments))
    if play_steps(state.steps):
        tally = games_won(state)
        lines.append('Games won: ' + ', '.join(f'{seat_names[seat]} {tally[seat]}' for seat in SEATS))
    lines.append(share_url)
    return lines


def score_line(seat_names, host_score, guest_score):
    if host_score is None or guest_score is None:
        return ''
    return f'{seat_names[Seat.HOST]} {host_score} – {guest_score} {seat_names[Seat.GUEST]}'


def summary_heading(steps, step):
    detail = wave_detail(step)
    label = step_label(steps, step)
    return f'{label} ({detail})' if detail else label


def played_deck_fragment(plan, seat, seat_names, deck_names):
    if not plan.is_assigned:
        return f'{deck_names.get(plan.brought_by_seat.get(seat), "no deck")} (brought by {seat_names[seat]})'
    chains = plan.chains_for(seat)
    pilot = seat_names[seat] if chains is None else f'{seat_names[seat]}, {chains} chains'
    return f'{deck_names.get(plan.played_by_seat.get(seat), "no deck")} ({pilot})'


def play_summary_line(state, step, plan, seat_names, deck_names, scores):
    matchup = ' vs '.join(played_deck_fragment(plan, seat, seat_names, deck_names) for seat in SEATS)
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
    summary = f'{game_label(state.steps, step)} ({GameType(plan.game_type).label}): {matchup} - {outcome}'
    if plan.first_deck_id is not None:
        summary += f' - {deck_names.get(plan.first_deck_id, "?")} goes first'
    return summary
