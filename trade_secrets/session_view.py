from dataclasses import dataclass, field

from django.urls import reverse
from django.utils.translation import gettext as _

from . import engine
from .engine import Action, AdaptiveStage, DeckStatus, GameType, Phase, PlayedDeckRule, Seat

ACTIVE_POLL_INTERVAL_MS = 2500
FINISHED_POLL_INTERVAL_MS = 15000

ACTION_ICONS = {
    Action.SUBMIT: 'deck',
    Action.BAN: 'ban',
    Action.SAFE: 'shield',
    Action.STEAL: 'swap',
    Action.PLAY: 'play',
    Action.BAN_MATCHUP: 'ban',
}

PLAY_RULE_HINTS = {
    PlayedDeckRule.INELIGIBLE: 'Played decks cannot be played again.',
    PlayedDeckRule.ELIGIBLE: 'Played decks can be played again.',
    PlayedDeckRule.LOSING_ONLY: 'Decks that win cannot be played again.',
}

PLAY_INSTRUCTIONS = {
    GameType.ARCHON: 'Pick your deck for {game}',
    GameType.REVERSAL: 'Pick the deck {opponent} will play in {game}',
    GameType.ADAPTIVE: 'Pick the deck you bring to {game}',
}

GAME_TYPE_HINTS = {
    GameType.ARCHON: '',
    GameType.REVERSAL: 'Reversal: you swap decks for this game. ',
    GameType.ADAPTIVE: "Adaptive: you'll each choose which of the two decks to play, and bid chains if you agree. ",
}

PAST_TENSE = {
    Action.BAN: 'banned',
    Action.BAN_MATCHUP: 'banned',
    Action.SAFE: 'safed',
    Action.STEAL: 'stole',
}

REVEAL_TITLES = {
    Action.SUBMIT: 'Lineups revealed',
    Action.BAN: 'Bans revealed',
    Action.SAFE: 'Safes revealed',
    Action.STEAL: 'Heist complete',
    Action.BAN_MATCHUP: 'Matchup bans revealed',
}


class Role:
    PLAYER = 'player'
    INVITEE = 'invitee'
    ANONYMOUS_INVITEE = 'anonymous-invitee'
    SPECTATOR = 'spectator'


class ActionState:
    SUBMIT_DECKS = 'submit-decks'
    SUBMIT_DECKS_LOCKED = 'submit-decks-locked'
    PICK = 'pick'
    WAITING = 'waiting'
    AWAITING_RESULT = 'awaiting-result'
    FINISHED = 'finished'
    INVITE_JOIN = 'invite-join'
    INVITE_LOGIN = 'invite-login'
    SPECTATOR = 'spectator'


@dataclass
class DeckBadge:
    kind: str
    icon: str
    label: str
    short_label: str = ''
    is_featured: bool = False


@dataclass
class DeckCard:
    session_deck_id: int
    deck: object
    status: str
    badges: list = field(default_factory=list)
    is_selectable: bool = False
    is_selected: bool = False
    is_sidelined: bool = False
    has_anchor: bool = True


@dataclass
class FeaturedSeat:
    name: str
    cards: list


@dataclass
class BidTrailEntry:
    name: str
    chains: int


@dataclass
class AdaptivePanel:
    stage: str
    can_act: bool
    cards: list
    has_locked_preference: bool = False
    contested_deck_name: str = ''
    leader_name: str = ''
    is_viewer_leading: bool = False
    is_opening_bid: bool = True
    high_bid: int = 0
    bid_trail: list = field(default_factory=list)
    is_viewer_turn: bool = False
    waiting_on_name: str = ''
    minimum_raise: int = 0
    maximum_bid: int = engine.MAXIMUM_CHAIN_BID
    can_raise: bool = True

    @property
    def is_choosing(self):
        return self.stage == AdaptiveStage.PREFERENCE

    @property
    def is_bidding(self):
        return self.stage == AdaptiveStage.BIDDING


@dataclass
class FeaturedGame:
    order: int
    label: str
    type_label: str
    seats: list
    adaptive: object = None
    has_result: bool = False
    winner_name: str = ''
    score_line: str = ''


@dataclass
class StolenGhost:
    deck: object
    taken_by: str


@dataclass
class LineupView:
    seat: str
    owner_name: str
    is_mine: bool
    cards: list = field(default_factory=list)
    ghosts: list = field(default_factory=list)
    facedown_count: int = 0
    is_hidden: bool = False
    is_targetable: bool = False

    @property
    def facedown_slots(self):
        return range(self.facedown_count)

    @property
    def in_play_count(self):
        return sum(1 for card in self.cards if card.status not in (DeckStatus.BANNED, DeckStatus.INELIGIBLE))

    @property
    def out_count(self):
        return len(self.cards) - self.in_play_count


@dataclass
class RailStep:
    number: int
    label: str
    icon: str
    is_done: bool
    is_current: bool
    is_blocked: bool
    detail: str = ''


@dataclass
class SeatPicks:
    name: str
    decks: list


@dataclass
class HistoryEntry:
    order: int
    number: int
    action: str
    icon: str
    title: str
    reveal_title: str
    verb: str
    subtitle: str
    seat_picks: list
    is_play: bool = False
    game_number: int = 0
    winner_name: str = ''
    score_line: str = ''
    has_result: bool = False
    can_record: bool = False
    can_reset: bool = False
    is_result_locked: bool = False
    is_banned: bool = False
    is_awaiting_ban: bool = False
    warns_about_eligibility: bool = False


@dataclass
class MatchupCard:
    order: int
    label: str
    seat_decks: list
    is_selected: bool = False


@dataclass
class SeatPresence:
    name: str
    is_viewer: bool
    has_locked_in: bool
    needs_to_act: bool


@dataclass
class SessionView:
    session: object
    role: str
    viewer_seat: str
    phase: str
    action_state: str
    stage_key: str
    version: int
    poll_interval_ms: int
    share_url: str
    host_name: str
    guest_name: str
    opponent_name: str
    rail: list
    current_step_number: int
    step_total: int
    instruction: str
    instruction_hint: str
    lineups: list
    matchup_choices: list
    presence: list
    history: list
    last_reveal: object
    blocking_game_number: int
    required_pick_count: int
    pick_step_order: int
    pick_noun: str
    has_pending_pick: bool
    summary_text: str
    games_won: list
    has_results: bool
    featured_games: list
    featured_games_title: str

    @property
    def is_player(self):
        return self.role == Role.PLAYER

    @property
    def is_finished(self):
        return self.phase in engine.FINISHED_PHASES

    @property
    def is_waiting_for_guest(self):
        return self.phase == Phase.WAITING_FOR_GUEST

    @property
    def shows_share_card(self):
        return self.is_player and self.viewer_seat == Seat.HOST and self.is_waiting_for_guest

    @property
    def has_revealed_lineups(self):
        return self.session.revealed_step_count > 0


def template_rail(step_specs):
    return [
        RailStep(
            number=step.order + 1,
            label=engine.step_label(step_specs, step),
            icon=ACTION_ICONS[step.action],
            is_done=False,
            is_current=False,
            is_blocked=False,
            detail=engine.wave_detail(step),
        )
        for step in step_specs
    ]


def template_summary(step_specs):
    fragments = []
    for step in step_specs:
        if step.is_submit:
            fragments.append(_('{count} decks').format(count=step.quantity))
        elif step.is_play:
            fragments.append(_('play'))
        elif step.quantity > 1:
            fragments.append(f'{str(Action(step.action).label).lower()} {step.quantity}')
        else:
            fragments.append(str(Action(step.action).label).lower())
    collapsed = []
    for fragment in fragments:
        if collapsed and collapsed[-1][0] == fragment:
            collapsed[-1][1] += 1
        else:
            collapsed.append([fragment, 1])
    return ' · '.join(
        f'{fragment} ×{count}' if count > 1 else fragment for fragment, count in collapsed)


def build_session_view(session, viewer, request=None):
    builder = SessionViewBuilder(session, viewer, request)
    return builder.build()


class SessionViewBuilder:
    def __init__(self, session, viewer, request):
        self.session = session
        self.viewer = viewer
        self.request = request
        self.template_steps = session.template_steps()
        self.state = session.build_engine_state()
        self.viewer_seat = session.seat_for(viewer)
        self.seat_names = session.seat_names()
        self.session_decks = {
            session_deck.id: session_deck
            for session_deck in session.decks.select_related(
                'deck__set', 'deck__house_1', 'deck__house_2', 'deck__house_3')
        }
        self.results = {result.step.order: result for result in session.results.select_related('step')}
        self.phase = engine.phase(self.state, session.has_guest)
        self.current_step = self.state.current_step
        self.submitted_seats = self.current_submitted_seats()
        self.pending_pick_ids = self.viewer_pending_pick_ids()
        self.picks_matchups = self.current_step is not None and self.current_step.is_matchup_ban
        self.game_plans = session.game_plans()
        self.featured_play_orders = self.orders_of_plays_to_feature()
        self.featured_deck_ids = self.ids_of_decks_in_featured_plays()
        self.game_card_orders = self.orders_of_games_with_cards()

    def build(self):
        role = self.role()
        required_pick_count = self.viewer_required_pick_count()
        history = self.history()
        return SessionView(
            session=self.session,
            role=role,
            viewer_seat=self.viewer_seat,
            phase=self.phase,
            action_state=self.action_state(role, required_pick_count),
            stage_key=self.stage_key(),
            version=self.session.version,
            poll_interval_ms=self.poll_interval_ms(),
            share_url=self.share_url(),
            host_name=self.seat_names[Seat.HOST],
            guest_name=self.seat_names[Seat.GUEST],
            opponent_name=self.opponent_name(),
            rail=self.rail(),
            current_step_number=self.current_step.order + 1 if self.current_step else len(self.template_steps),
            step_total=len(self.template_steps),
            instruction=self.instruction(role, required_pick_count),
            instruction_hint=self.instruction_hint(),
            lineups=self.lineups(required_pick_count),
            matchup_choices=self.matchup_choices(required_pick_count),
            presence=self.presence(),
            history=history,
            last_reveal=history[-1] if history else None,
            blocking_game_number=self.blocking_game_number(),
            required_pick_count=required_pick_count,
            pick_step_order=self.current_step.order if self.current_step else -1,
            pick_noun=_('matchup') if self.picks_matchups else _('deck'),
            has_pending_pick=self.viewer_seat in self.submitted_seats,
            summary_text='\n'.join(self.summary_lines()),
            games_won=self.games_won(),
            has_results=bool(self.results),
            featured_games=self.featured_games(),
            featured_games_title=self.featured_games_title(),
        )

    def poll_interval_ms(self):
        if self.phase in engine.FINISHED_PHASES and not self.labels_of_unsettled_adaptive_games():
            return FINISHED_POLL_INTERVAL_MS
        return ACTIVE_POLL_INTERVAL_MS

    def labels_of_unsettled_adaptive_games(self):
        return [
            engine.game_label(self.state.steps, self.state.steps[order])
            for order in self.game_card_orders if not self.game_plans[order].is_assigned
        ]

    def orders_of_plays_to_feature(self):
        if self.phase not in engine.FINISHED_PHASES:
            return set()
        return set(engine.unbanned_matchup_orders(self.state))

    def ids_of_decks_in_featured_plays(self):
        return {
            deck_id
            for revealed in self.featured_plays()
            for deck_id in engine.all_picked_ids(revealed.picks_by_seat)
        }

    def featured_plays(self):
        return [revealed for revealed in self.state.history if revealed.step.order in self.featured_play_orders]

    def orders_of_games_with_cards(self):
        if self.phase in engine.FINISHED_PHASES:
            return sorted(self.featured_play_orders)
        return [
            order for order, plan in sorted(self.game_plans.items())
            if plan.game_type != GameType.ARCHON and order not in self.results and self.is_playable_game(order)
        ]

    def is_playable_game(self, order):
        return order not in self.state.banned_matchup_orders and not engine.is_awaiting_matchup_ban(
            self.state.steps, self.state.steps[order], self.state.revealed_count)

    def viewer_label(self, seat):
        return _('You') if seat == self.viewer_seat else self.seat_names[seat]

    def featured_games(self):
        return [self.featured_game_for(order) for order in self.game_card_orders]

    def featured_game_for(self, order):
        plan = self.game_plans[order]
        result = self.results.get(order)
        game = FeaturedGame(
            order=order,
            label=engine.game_label(self.state.steps, self.state.steps[order]),
            type_label=str(GameType(plan.game_type).label),
            seats=[
                FeaturedSeat(
                    name=self.viewer_label(seat),
                    cards=[self.game_card(plan, plan.played_by_seat[seat], pilot_seat=seat)])
                for seat in engine.SEATS if plan.is_assigned
            ],
        )
        if not plan.is_assigned:
            game.adaptive = self.adaptive_panel(plan)
        if result is not None:
            game.has_result = True
            game.winner_name = self.seat_names[result.winner_seat]
            game.score_line = engine.score_line(self.seat_names, result.host_score, result.guest_score)
        return game

    def game_card(self, plan, session_deck_id, pilot_seat=None, is_selectable=False, is_selected=False):
        return DeckCard(
            session_deck_id=session_deck_id,
            deck=self.session_decks[session_deck_id].deck,
            status=DeckStatus.AVAILABLE,
            badges=self.game_card_badges(plan, session_deck_id, pilot_seat),
            is_selectable=is_selectable,
            is_selected=is_selected,
            has_anchor=False,
        )

    def game_card_badges(self, plan, session_deck_id, pilot_seat):
        badges = []
        owner_seat = plan.seat_that_brought(session_deck_id)
        if plan.game_type != GameType.ARCHON and owner_seat != pilot_seat:
            owner_label = _('Your deck') if owner_seat == self.viewer_seat else _("{name}'s deck").format(
                name=self.seat_names[owner_seat])
            badges.append(DeckBadge(kind='owner', icon='deck', label=owner_label, short_label=owner_label))
        if plan.first_deck_id == session_deck_id:
            badges.append(DeckBadge(kind='first', icon='play', label=_('Goes first'), short_label=_('1st')))
        if plan.stage == AdaptiveStage.BIDDING and plan.contested_deck_id == session_deck_id:
            badges.append(DeckBadge(kind='contested', icon='swap', label=_('Both want this'), short_label=_('Both')))
        chains = plan.chains_for(pilot_seat) if pilot_seat else None
        if chains is not None:
            chains_label = _('{count} chains').format(count=chains)
            badges.append(DeckBadge(kind='chains', icon='lock', label=chains_label, short_label=str(chains)))
        return badges

    def adaptive_panel(self, plan):
        can_act = bool(self.viewer_seat)
        is_choosing = plan.stage == AdaptiveStage.PREFERENCE
        own_preference = plan.preferences.get(self.viewer_seat) if is_choosing else None
        panel = AdaptivePanel(
            stage=plan.stage,
            can_act=can_act,
            cards=[
                self.game_card(
                    plan, plan.brought_by_seat[seat],
                    is_selectable=can_act and is_choosing,
                    is_selected=plan.brought_by_seat[seat] == own_preference)
                for seat in engine.SEATS
            ],
            has_locked_preference=own_preference is not None,
        )
        if plan.stage == AdaptiveStage.BIDDING:
            self.fill_bidding_panel(panel, plan)
        return panel

    def fill_bidding_panel(self, panel, plan):
        opening_seat = plan.seat_that_brought(plan.contested_deck_id)
        panel.contested_deck_name = self.deck_names()[plan.contested_deck_id]
        panel.leader_name = self.viewer_label(plan.high_bidder)
        panel.is_viewer_leading = plan.high_bidder == self.viewer_seat
        panel.is_opening_bid = not plan.bids
        panel.high_bid = plan.high_bid
        panel.bid_trail = [BidTrailEntry(self.viewer_label(opening_seat), engine.OPENING_CHAIN_BID)] + [
            BidTrailEntry(self.viewer_label(bid.seat), bid.chains) for bid in plan.bids]
        panel.is_viewer_turn = plan.seat_to_bid == self.viewer_seat
        panel.waiting_on_name = self.seat_names[plan.seat_to_bid]
        panel.minimum_raise = plan.minimum_raise
        panel.can_raise = plan.can_raise

    def featured_games_title(self):
        if any(engine.is_matchup(self.state.steps, self.state.steps[order]) for order in self.game_card_orders):
            return _('Matchups')
        return _('Games')

    def play_seat_picks(self, order):
        plan = self.game_plans[order]
        deck_names = self.deck_names()
        if not plan.is_assigned:
            return [
                SeatPicks(
                    name=_('{name} brought').format(name=self.viewer_label(seat)),
                    decks=[deck_names[plan.brought_by_seat[seat]]])
                for seat in engine.SEATS
            ]
        return [
            SeatPicks(name=self.pilot_label(plan, seat), decks=[deck_names[plan.played_by_seat[seat]]])
            for seat in engine.SEATS
        ]

    def pilot_label(self, plan, seat):
        chains = plan.chains_for(seat)
        if chains is None:
            return self.viewer_label(seat)
        return _('{name}, {count} chains').format(name=self.viewer_label(seat), count=chains)

    def play_subtitle(self, order):
        plan = self.game_plans[order]
        type_label = str(GameType(plan.game_type).label)
        if plan.first_deck_id is None:
            return type_label
        return _('{type} · {deck} goes first').format(type=type_label, deck=self.deck_names()[plan.first_deck_id])

    def adaptive_signature(self):
        return '.'.join(
            f'{order}{plan.stage[0]}{len(plan.bids)}{int(self.viewer_seat in plan.preferences)}'
            for order, plan in sorted(self.game_plans.items()) if plan.is_adaptive)

    def role(self):
        if self.viewer_seat:
            return Role.PLAYER
        if self.session.has_guest:
            return Role.SPECTATOR
        if self.viewer.is_authenticated:
            return Role.INVITEE
        return Role.ANONYMOUS_INVITEE

    def current_submitted_seats(self):
        if self.current_step is None:
            return set()
        return set(self.session.submissions.filter(
            step__order=self.current_step.order).values_list('seat', flat=True))

    def viewer_pending_pick_ids(self):
        if not self.viewer_seat or self.current_step is None or self.current_step.is_submit:
            return set()
        submission = self.session.pending_submission_for(self.viewer_seat)
        if submission is None:
            return set()
        return set(submission.picked_ids())

    def viewer_required_pick_count(self):
        if not self.viewer_seat or self.phase != Phase.SELECTING:
            return 0
        return engine.required_pick_count(self.state, self.current_step, self.viewer_seat)

    def action_state(self, role, required_pick_count):
        if role == Role.INVITEE:
            return ActionState.INVITE_JOIN
        if role == Role.ANONYMOUS_INVITEE:
            return ActionState.INVITE_LOGIN
        if role == Role.SPECTATOR:
            return ActionState.FINISHED if self.phase in engine.FINISHED_PHASES else ActionState.SPECTATOR
        if self.phase in (Phase.WAITING_FOR_GUEST, Phase.SUBMITTING_DECKS):
            if self.viewer_seat in self.submitted_seats:
                return ActionState.SUBMIT_DECKS_LOCKED
            return ActionState.SUBMIT_DECKS
        if self.phase == Phase.AWAITING_RESULT:
            return ActionState.AWAITING_RESULT
        if self.phase in engine.FINISHED_PHASES:
            return ActionState.FINISHED
        if required_pick_count == 0:
            return ActionState.WAITING
        return ActionState.PICK

    def stage_key(self):
        phase = self.phase
        if self.viewer_seat and phase == Phase.WAITING_FOR_GUEST:
            phase = Phase.SUBMITTING_DECKS
        results_signature = '.'.join(
            f'{order}{result.winner_seat[0]}' for order, result in sorted(self.results.items()))
        own_pending = int(self.viewer_seat in self.submitted_seats)
        return (
            f'{phase}:{self.session.revealed_step_count}:{own_pending}:{results_signature}'
            f':{self.adaptive_signature()}')

    def share_url(self):
        path = reverse('trade_secrets:session-detail', args=[self.session.code])
        return self.request.build_absolute_uri(path) if self.request else path

    def opponent_name(self):
        return self.seat_names[engine.opponent_of(self.viewer_seat)] if self.viewer_seat else ''

    def rail(self):
        blocking_step = engine.missing_result_step(self.state)
        steps = []
        for step in self.state.steps:
            is_done = step.order < self.state.revealed_count
            steps.append(RailStep(
                number=step.order + 1,
                label=engine.step_label(self.state.steps, step),
                icon=ACTION_ICONS[step.action],
                is_done=is_done,
                is_current=self.current_step is not None and step.order == self.current_step.order,
                is_blocked=blocking_step is not None and step.order == blocking_step.order,
                detail=engine.wave_detail(step),
            ))
        return steps

    def instruction(self, role, required_pick_count):
        step = self.current_step
        if self.phase == Phase.WAITING_FOR_GUEST and role != Role.PLAYER:
            return _('Waiting for an opponent')
        if self.phase in engine.FINISHED_PHASES and self.labels_of_unsettled_adaptive_games():
            return _('Settle who plays which deck in {games}').format(
                games=_(' and ').join(self.labels_of_unsettled_adaptive_games()).lower())
        if self.phase == Phase.COMPLETE and self.unplayed_matchup_labels():
            return _('Play {matchups} and record the result').format(
                matchups=_(' or ').join(self.unplayed_matchup_labels()).lower())
        if self.phase == Phase.COMPLETE:
            return _('All done')
        if self.phase == Phase.CONCLUDED:
            return _('Match decided')
        if self.phase == Phase.AWAITING_RESULT:
            return _('Record game {number} to continue').format(number=self.blocking_game_number())
        if step.is_submit and self.viewer_seat in self.submitted_seats:
            return _('Your decks are locked in')
        if step.is_submit:
            return _('Submit {count} decks').format(count=step.quantity)
        if role != Role.PLAYER:
            return engine.step_label(self.state.steps, step)
        opponent = self.opponent_name()
        if step.is_play:
            game = engine.game_label(self.state.steps, step).lower()
            if required_pick_count == 0:
                return _('No deck left for {game}').format(game=game)
            return _(PLAY_INSTRUCTIONS[step.game_type]).format(game=game, opponent=opponent)
        if step.is_matchup_ban:
            return _('Ban 1 matchup')
        if required_pick_count == 0:
            return _('Nothing to {action} this step').format(action=str(Action(step.action).label).lower())
        templates = {
            Action.BAN: _("Ban {count} of {name}'s decks"),
            Action.SAFE: _('Safe {count} of your decks'),
            Action.STEAL: _("Steal {count} of {name}'s decks"),
        }
        return templates[step.action].format(count=required_pick_count, name=opponent)

    def instruction_hint(self):
        step = self.current_step
        if step is None or self.phase in engine.FINISHED_PHASES:
            return ''
        if step.is_submit and self.viewer_seat in self.submitted_seats and self.session.has_guest:
            return _('You can change them until {name} submits.').format(name=self.opponent_name())
        if step.is_submit:
            return _('Hidden from your opponent until you both submit.')
        if step.is_play and engine.is_matchup(self.state.steps, step):
            return (
                _(GAME_TYPE_HINTS[step.game_type]) + _('This matchup is played after the matchup bans. ')
                + _(PLAY_RULE_HINTS[step.played_deck_rule]))
        if step.is_play:
            return _(GAME_TYPE_HINTS[step.game_type]) + _(PLAY_RULE_HINTS[step.played_deck_rule])
        hints = {
            Action.BAN_MATCHUP: _("Banned matchups won't be played. You may both ban the same one."),
            Action.BAN: _('Banned decks are out for the rest of the match.'),
            Action.SAFE: _('Safe decks cannot be banned or stolen.'),
            Action.STEAL: _('Stolen decks join your lineup. Steals resolve at the same time.'),
        }
        return hints[step.action]

    def lineup_order(self):
        if self.viewer_seat:
            return [engine.opponent_of(self.viewer_seat), self.viewer_seat]
        return [Seat.GUEST, Seat.HOST]

    def target_seat(self):
        step = self.current_step
        if not self.viewer_seat or step is None or self.phase != Phase.SELECTING or step.is_matchup_ban:
            return None
        if step.action in (Action.BAN, Action.STEAL):
            return engine.opponent_of(self.viewer_seat)
        return self.viewer_seat

    def lineups(self, required_pick_count):
        target_seat = self.target_seat() if required_pick_count else None
        choice_ids = set(engine.choices_for(self.state, self.current_step, self.viewer_seat)) if target_seat else set()
        return [self.lineup_for(seat, target_seat, choice_ids) for seat in self.lineup_order()]

    def matchup_choices(self, required_pick_count):
        if not self.picks_matchups or not required_pick_count:
            return []
        return [
            MatchupCard(
                order=order,
                label=engine.game_label(self.state.steps, self.state.steps[order]),
                seat_decks=self.play_seat_picks(order),
                is_selected=order in self.pending_pick_ids,
            )
            for order in engine.choices_for(self.state, self.current_step, self.viewer_seat)
        ]

    def unplayed_matchup_labels(self):
        unbanned_matchup_orders = [
            order for order in engine.unbanned_matchup_orders(self.state)
            if engine.is_matchup(self.state.steps, self.state.steps[order])
        ]
        if any(order in self.results for order in unbanned_matchup_orders):
            return []
        return [engine.game_label(self.state.steps, self.state.steps[order]) for order in unbanned_matchup_orders]

    def lineup_for(self, seat, target_seat, choice_ids):
        lineup = LineupView(
            seat=seat,
            owner_name=self.seat_names[seat],
            is_mine=seat == self.viewer_seat,
            is_targetable=seat == target_seat,
        )
        if not self.lineups_are_revealed():
            if seat == self.viewer_seat:
                lineup.cards = [self.hidden_phase_card(session_deck) for session_deck in self.decks_submitted_by(seat)]
            else:
                lineup.is_hidden = True
                lineup.facedown_count = len(self.decks_submitted_by(seat)) if seat in self.submitted_seats else 0
            return lineup
        for deck_state in self.state.decks_held_by(seat):
            lineup.cards.append(self.card_for(deck_state, choice_ids if seat == target_seat else set()))
        for deck_state in self.state.decks_submitted_by(seat):
            if deck_state.holder_seat != seat:
                lineup.ghosts.append(StolenGhost(
                    deck=self.session_decks[deck_state.id].deck,
                    taken_by=self.seat_names[deck_state.holder_seat]))
        return lineup

    def lineups_are_revealed(self):
        return self.state.revealed_count > 0

    def decks_submitted_by(self, seat):
        return [session_deck for session_deck in self.session_decks.values() if session_deck.seat == seat]

    def hidden_phase_card(self, session_deck):
        return DeckCard(
            session_deck_id=session_deck.id,
            deck=session_deck.deck,
            status=DeckStatus.AVAILABLE,
        )

    def card_for(self, deck_state, choice_ids):
        return DeckCard(
            session_deck_id=deck_state.id,
            deck=self.session_decks[deck_state.id].deck,
            status=engine.deck_status(deck_state),
            badges=self.badges_for(deck_state),
            is_selectable=deck_state.id in choice_ids,
            is_selected=not self.picks_matchups and deck_state.id in self.pending_pick_ids,
            is_sidelined=bool(self.featured_deck_ids) and deck_state.id not in self.featured_deck_ids,
        )

    def badges_for(self, deck_state):
        badges = []
        if deck_state.is_banned:
            badges.append(self.wave_badge('banned', 'ban', _('Banned'), deck_state.banned_at_order))
        elif deck_state.is_spent:
            badges.append(self.out_badge(deck_state))
        if deck_state.is_safed:
            badges.append(self.wave_badge('safed', 'shield', _('Safed'), deck_state.safed_at_order))
        if deck_state.is_held_by_opponent_of_owner:
            stolen_label = _('Stolen from {name}').format(name=self.seat_names[deck_state.original_seat])
            badges.append(self.wave_badge('stolen', 'swap', stolen_label, deck_state.stolen_at_orders[-1]))
        badges.extend(
            self.game_badge(deck_state, order)
            for order in deck_state.played_at_orders
            if order != deck_state.spent_at_order)
        return badges

    def out_badge(self, deck_state):
        number = engine.game_number_for_order(self.state.steps, deck_state.spent_at_order)
        short_label = _('{number}W').format(number=number) if deck_state.spent_by_winning else str(number)
        return DeckBadge(
            kind='ineligible', icon='play',
            label=engine.ineligible_reason(self.state, deck_state), short_label=short_label,
            is_featured=deck_state.spent_at_order in self.featured_play_orders)

    def wave_badge(self, kind, icon, status_text, order):
        suffix = engine.wave_suffix(self.state.steps, order)
        label = status_text
        if suffix:
            label = f'{status_text} · {engine.step_label(self.state.steps, self.state.steps[order])}'
        return DeckBadge(kind=kind, icon=icon, label=label, short_label=suffix)

    def game_badge(self, deck_state, order):
        step = self.state.steps[order]
        number = engine.game_number_for_order(self.state.steps, order)
        tag = f"{_('M') if engine.is_matchup(self.state.steps, step) else _('G')}{number}"
        winner = self.state.winners.get(order)
        is_featured = order in self.featured_play_orders
        if order in self.state.banned_matchup_orders:
            return DeckBadge(kind='game-banned', icon='play', label=_('{tag} Banned').format(tag=tag),
                             short_label=str(number))
        if winner is None:
            return DeckBadge(kind='game', icon='play', label=tag, short_label=str(number), is_featured=is_featured)
        if self.played_by_winner(order, deck_state):
            return DeckBadge(kind='game', icon='play', label=_('{tag} Won').format(tag=tag),
                             short_label=_('{number}W').format(number=number), is_featured=is_featured)
        return DeckBadge(kind='game', icon='play', label=_('{tag} Lost').format(tag=tag),
                         short_label=_('{number}L').format(number=number), is_featured=is_featured)

    def played_by_winner(self, order, deck_state):
        revealed = next(entry for entry in self.state.history if entry.step.order == order)
        winner = self.state.winners.get(order)
        return deck_state.id in revealed.picks_by_seat.get(winner, ())

    def presence(self):
        if not self.session.has_guest or self.current_step is None or self.phase in engine.FINISHED_PHASES:
            return []
        if self.phase == Phase.AWAITING_RESULT:
            return []
        seats_to_act = (
            set(engine.SEATS) if self.current_step.is_submit
            else set(engine.seats_needing_picks(self.state, self.current_step)))
        return [
            SeatPresence(
                name=self.seat_names[seat],
                is_viewer=seat == self.viewer_seat,
                has_locked_in=seat in self.submitted_seats,
                needs_to_act=seat in seats_to_act,
            )
            for seat in self.lineup_order()[::-1]
        ]

    def deck_names(self):
        return {
            session_deck_id: session_deck.deck.name or str(session_deck.deck_id)
            for session_deck_id, session_deck in self.session_decks.items()
        }

    def history(self):
        deck_names = self.deck_names()
        entries = []
        for revealed in self.state.history:
            step = revealed.step
            entry = HistoryEntry(
                order=step.order,
                number=step.order + 1,
                action=step.action,
                icon=ACTION_ICONS[step.action],
                title=self.history_title(step),
                subtitle=engine.wave_detail(step),
                reveal_title=self.reveal_title(step),
                verb=PAST_TENSE.get(step.action, ''),
                seat_picks=[
                    SeatPicks(
                        name=_('You') if seat == self.viewer_seat else self.seat_names[seat],
                        decks=self.picked_names(step, revealed.picks_by_seat.get(seat, ()), deck_names))
                    for seat in engine.SEATS
                ],
            )
            if step.is_play:
                self.fill_play_entry(entry, step)
            entries.append(entry)
        return entries

    def picked_names(self, step, picked_ids, deck_names):
        if step.is_matchup_ban:
            return [engine.game_label(self.state.steps, self.state.steps[order]) for order in picked_ids]
        return [deck_names[deck_id] for deck_id in picked_ids]

    def history_title(self, step):
        if step.is_submit:
            return _('Lineups revealed')
        return engine.step_label(self.state.steps, step)

    def reveal_title(self, step):
        if step.is_play:
            return self.history_title(step)
        return _(REVEAL_TITLES[step.action])

    def fill_play_entry(self, entry, step):
        result = self.results.get(step.order)
        entry.is_play = True
        entry.seat_picks = self.play_seat_picks(step.order)
        entry.subtitle = self.play_subtitle(step.order)
        entry.game_number = engine.game_number_for_order(self.state.steps, step.order)
        entry.has_result = result is not None
        entry.is_result_locked = result is not None and engine.is_result_locked(
            self.state.steps, step.order, self.results.keys())
        entry.is_banned = step.order in self.state.banned_matchup_orders
        entry.is_awaiting_ban = engine.is_awaiting_matchup_ban(
            self.state.steps, step, self.state.revealed_count)
        entry.warns_about_eligibility = step.played_deck_rule == PlayedDeckRule.LOSING_ONLY
        if result is not None:
            entry.winner_name = self.seat_names[result.winner_seat]
            entry.score_line = engine.score_line(self.seat_names, result.host_score, result.guest_score)
        if self.viewer_seat and not entry.is_banned and not entry.is_awaiting_ban:
            entry.can_record = not entry.is_result_locked
            entry.can_reset = entry.has_result and not entry.is_result_locked

    def blocking_game_number(self):
        step = engine.missing_result_step(self.state)
        if step is None:
            return 0
        return engine.game_number_for_order(self.state.steps, step.order)

    def summary_lines(self):
        if not self.lineups_are_revealed():
            return []
        return engine.results_summary_lines(
            self.state,
            self.session.template.name,
            self.session.code,
            self.seat_names,
            self.deck_names(),
            {order: (result.host_score, result.guest_score) for order, result in self.results.items()},
            self.share_url(),
            self.game_plans,
        )

    def games_won(self):
        tally = engine.games_won(self.state)
        return [(self.seat_names[seat], tally[seat]) for seat in engine.SEATS]
