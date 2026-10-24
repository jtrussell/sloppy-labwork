from dataclasses import dataclass, field

from django.urls import reverse
from django.utils.translation import gettext as _

from . import engine
from .engine import Action, DeckStatus, Phase, PlayedDeckRule, Seat

ACTIVE_POLL_INTERVAL_MS = 2500
FINISHED_POLL_INTERVAL_MS = 15000

ACTION_ICONS = {
    Action.SUBMIT: 'deck',
    Action.BAN: 'ban',
    Action.SAFE: 'shield',
    Action.STEAL: 'swap',
    Action.PLAY: 'play',
}

STATUS_ICONS = {
    DeckStatus.BANNED: 'ban',
    DeckStatus.SAFED: 'shield',
    DeckStatus.STOLEN: 'swap',
    DeckStatus.PLAYED: 'play',
}

PLAY_RULE_HINTS = {
    PlayedDeckRule.INELIGIBLE: 'Played decks cannot be played again.',
    PlayedDeckRule.ELIGIBLE: 'Played decks can be played again.',
    PlayedDeckRule.LOSING_ONLY: 'Decks that win cannot be played again.',
}

PAST_TENSE = {
    Action.BAN: 'banned',
    Action.SAFE: 'safed',
    Action.STEAL: 'stole',
}

REVEAL_TITLES = {
    Action.SUBMIT: 'Lineups revealed',
    Action.BAN: 'Bans revealed',
    Action.SAFE: 'Safes revealed',
    Action.STEAL: 'Heist complete',
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
class DeckCard:
    session_deck_id: int
    deck: object
    status: str
    status_label: str
    status_icon: str
    game_tags: list = field(default_factory=list)
    stolen_from: str = ''
    is_selectable: bool = False
    is_selected: bool = False


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
    seat_picks: list
    is_play: bool = False
    game_number: int = 0
    winner_name: str = ''
    score: str = ''
    has_result: bool = False
    can_record: bool = False
    can_reset: bool = False
    is_result_locked: bool = False
    warns_about_eligibility: bool = False


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
    presence: list
    history: list
    last_reveal: object
    blocking_game_number: int
    required_pick_count: int
    pick_step_order: int
    has_pending_pick: bool
    summary_text: str
    games_won: list
    has_games: bool

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
            label=rail_label(step_specs, step),
            icon=ACTION_ICONS[step.action],
            is_done=False,
            is_current=False,
            is_blocked=False,
        )
        for step in step_specs
    ]


def rail_label(step_specs, step):
    if step.is_play:
        return _('Game {number}').format(number=engine.game_number_for_order(step_specs, step.order))
    if step.is_submit:
        return _('Submit {count}').format(count=step.quantity)
    label = str(Action(step.action).label)
    return f'{label} {step.quantity}' if step.quantity > 1 else label


def template_summary(step_specs):
    fragments = []
    for step in step_specs:
        if step.is_submit:
            fragments.append(_('{count} decks').format(count=step.quantity))
        elif step.is_play:
            fragments.append(_('play'))
        else:
            fragments.append(engine.step_label(step).lower())
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
            poll_interval_ms=FINISHED_POLL_INTERVAL_MS if self.phase in engine.FINISHED_PHASES else ACTIVE_POLL_INTERVAL_MS,
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
            presence=self.presence(),
            history=history,
            last_reveal=history[-1] if history else None,
            blocking_game_number=self.blocking_game_number(),
            required_pick_count=required_pick_count,
            pick_step_order=self.current_step.order if self.current_step else -1,
            has_pending_pick=self.viewer_seat in self.submitted_seats,
            summary_text='\n'.join(self.summary_lines()),
            games_won=self.games_won(),
            has_games=any(step.is_play for step in self.state.steps[:self.state.revealed_count]),
        )

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
        return {deck.id for deck in submission.decks.all()}

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
        return f'{phase}:{self.session.revealed_step_count}:{own_pending}:{results_signature}'

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
                label=self.short_step_label(step),
                icon=ACTION_ICONS[step.action],
                is_done=is_done,
                is_current=self.current_step is not None and step.order == self.current_step.order,
                is_blocked=blocking_step is not None and step.order == blocking_step.order,
            ))
        return steps

    def short_step_label(self, step):
        return rail_label(self.state.steps, step)

    def instruction(self, role, required_pick_count):
        step = self.current_step
        if self.phase == Phase.WAITING_FOR_GUEST and role != Role.PLAYER:
            return _('Waiting for an opponent')
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
            return engine.step_label(step) if not step.is_play else self.short_step_label(step)
        opponent = self.opponent_name()
        if step.is_play:
            game_number = engine.game_number_for_order(self.state.steps, step.order)
            if required_pick_count == 0:
                return _('No deck left for game {number}').format(number=game_number)
            return _('Pick your deck for game {number}').format(number=game_number)
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
        if step.is_play:
            return _(PLAY_RULE_HINTS[step.played_deck_rule])
        hints = {
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
        if not self.viewer_seat or step is None or self.phase != Phase.SELECTING:
            return None
        if step.action in (Action.BAN, Action.STEAL):
            return engine.opponent_of(self.viewer_seat)
        return self.viewer_seat

    def lineups(self, required_pick_count):
        target_seat = self.target_seat() if required_pick_count else None
        choice_ids = set(engine.choices_for(self.state, self.current_step, self.viewer_seat)) if target_seat else set()
        return [self.lineup_for(seat, target_seat, choice_ids) for seat in self.lineup_order()]

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
            status_label='',
            status_icon='',
        )

    def card_for(self, deck_state, choice_ids):
        status = engine.deck_status(deck_state)
        is_out = status == DeckStatus.INELIGIBLE
        return DeckCard(
            session_deck_id=deck_state.id,
            deck=self.session_decks[deck_state.id].deck,
            status=status,
            status_label=self.status_label(status, deck_state),
            status_icon=STATUS_ICONS.get(status, ''),
            game_tags=[] if is_out else self.game_tags(deck_state),
            stolen_from=(
                self.seat_names[deck_state.original_seat]
                if deck_state.is_held_by_opponent_of_owner else ''),
            is_selectable=deck_state.id in choice_ids,
            is_selected=deck_state.id in self.pending_pick_ids,
        )

    def status_label(self, status, deck_state):
        if status == DeckStatus.AVAILABLE:
            return ''
        if status == DeckStatus.STOLEN:
            return _('Stolen from {name}').format(name=self.seat_names[deck_state.original_seat])
        if status == DeckStatus.PLAYED:
            return ''
        if status == DeckStatus.INELIGIBLE:
            return engine.ineligible_reason(self.state, deck_state)
        return str(status.label)

    def game_tags(self, deck_state):
        tags = []
        for order in deck_state.played_at_orders:
            game_number = engine.game_number_for_order(self.state.steps, order)
            winner = self.state.winners.get(order)
            if winner is None:
                tags.append(_('G{number}').format(number=game_number))
            elif self.played_by_winner(order, deck_state):
                tags.append(_('G{number} Won').format(number=game_number))
            else:
                tags.append(_('G{number} Lost').format(number=game_number))
        return tags

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
        latest_result_order = max(self.results) if self.results else -1
        entries = []
        for revealed in self.state.history:
            step = revealed.step
            entry = HistoryEntry(
                order=step.order,
                number=step.order + 1,
                action=step.action,
                icon=ACTION_ICONS[step.action],
                title=self.history_title(step),
                reveal_title=self.reveal_title(step),
                verb=PAST_TENSE.get(step.action, ''),
                seat_picks=[
                    SeatPicks(
                        name=_('You') if seat == self.viewer_seat else self.seat_names[seat],
                        decks=[deck_names[deck_id] for deck_id in revealed.picks_by_seat.get(seat, ())])
                    for seat in engine.SEATS
                ],
            )
            if step.is_play:
                self.fill_play_entry(entry, step, latest_result_order)
            entries.append(entry)
        return entries

    def history_title(self, step):
        if step.is_submit:
            return _('Lineups revealed')
        if step.is_play:
            return _('Game {number}').format(number=engine.game_number_for_order(self.state.steps, step.order))
        return engine.step_label(step)

    def reveal_title(self, step):
        if step.is_play:
            return self.history_title(step)
        return _(REVEAL_TITLES[step.action])

    def fill_play_entry(self, entry, step, latest_result_order):
        result = self.results.get(step.order)
        entry.is_play = True
        entry.game_number = engine.game_number_for_order(self.state.steps, step.order)
        entry.has_result = result is not None
        entry.is_result_locked = result is not None and step.order < latest_result_order
        entry.warns_about_eligibility = step.played_deck_rule == PlayedDeckRule.LOSING_ONLY
        if result is not None:
            entry.winner_name = self.seat_names[result.winner_seat]
            entry.score = result.score
        if self.viewer_seat:
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
            {order: result.score for order, result in self.results.items()},
            self.share_url(),
        )

    def games_won(self):
        tally = engine.games_won(self.state)
        return [(self.seat_names[seat], tally[seat]) for seat in engine.SEATS]

