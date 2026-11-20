from . import engine
from .engine import SEATS, Seat
from .models import AdaptivePreference, AdaptiveSetup, ChainBid, PlayResult, SessionDeck, StepSubmission, TemplateStep

BANNED_MATCHUP_CELL = 'Banned'
PARTICIPANT_COUNT = len(SEATS)
PLAY_STEP_COLUMN_COUNT = 4 * PARTICIPANT_COUNT + 3


def load_step_specs_by_template_id(template_ids):
    step_specs_by_template_id = {template_id: [] for template_id in template_ids}
    steps = TemplateStep.objects.filter(template_id__in=template_ids).order_by('template_id', 'order')
    for step in steps:
        step_specs_by_template_id[step.template_id].append(step.to_spec())
    return step_specs_by_template_id


def get_step_headers(step_specs, column_prefix, participant_labels):
    headers = []
    for spec in step_specs:
        label = f'{column_prefix} {engine.step_label(step_specs, spec)}'
        if spec.is_play:
            headers.append(f'{label} type')
            headers.extend(f'{label} deck brought ({participant})' for participant in participant_labels)
            headers.extend(f'{label} deck played ({participant})' for participant in participant_labels)
            headers.extend(f'{label} chains ({participant})' for participant in participant_labels)
            headers.append(f'{label} first deck')
            headers.append(f'{label} winner')
            headers.extend(f'{label} score ({participant})' for participant in participant_labels)
        else:
            headers.extend(f'{label} ({participant})' for participant in participant_labels)
    return headers


class SessionExporter:
    def __init__(self, template_ids, sessions, selection_delimiter):
        self.selection_delimiter = selection_delimiter
        self.step_specs_by_template_id = load_step_specs_by_template_id(template_ids)
        session_ids = [session.id for session in sessions]
        self.deck_ids_by_session_deck_id = {}
        self.submitted_deck_ids = self.load_submitted_deck_ids(session_ids)
        self.picks = {}
        self.brought_session_deck_ids = {}
        self.banned_matchup_orders = {}
        self.load_submissions(sessions)
        self.results = {
            (result.session_id, result.step.order): result
            for result in PlayResult.objects.filter(session_id__in=session_ids).select_related('step')
        }
        self.adaptive_records = self.load_adaptive_records(session_ids)

    def load_submitted_deck_ids(self, session_ids):
        submitted_deck_ids = {}
        session_decks = SessionDeck.objects.filter(session_id__in=session_ids).order_by(
            'session_id', 'seat', 'sort_order').values_list('id', 'session_id', 'seat', 'deck_id')
        for session_deck_id, session_id, seat, deck_id in session_decks:
            submitted_deck_ids.setdefault((session_id, seat), []).append(str(deck_id))
            self.deck_ids_by_session_deck_id[session_deck_id] = str(deck_id)
        return submitted_deck_ids

    @staticmethod
    def load_adaptive_records(session_ids):
        records = {}

        def record_for(row):
            return records.setdefault((row.session_id, row.step.order), engine.AdaptiveRecord())

        for setup in AdaptiveSetup.objects.filter(session_id__in=session_ids).select_related('step'):
            record_for(setup).first_deck_id = setup.first_deck_id
        for preference in AdaptivePreference.objects.filter(session_id__in=session_ids).select_related('step'):
            record_for(preference).preferences[preference.seat] = preference.deck_id
        for bid in ChainBid.objects.filter(session_id__in=session_ids).select_related('step').order_by('sequence'):
            record_for(bid).bids.append(engine.ChainBidEntry(bid.seat, bid.chains))
        return records

    def load_submissions(self, sessions):
        revealed_step_counts = {session.id: session.revealed_step_count for session in sessions}
        submissions = StepSubmission.objects.filter(
            session_id__in=revealed_step_counts
        ).select_related('step').prefetch_related('decks', 'matchups')
        for submission in submissions:
            if submission.step.order >= revealed_step_counts[submission.session_id]:
                continue
            step_specs = self.step_specs_by_template_id.get(submission.step.template_id, [])
            if submission.step.action == engine.Action.BAN_MATCHUP:
                matchup_orders = [matchup.order for matchup in submission.matchups.all()]
                self.banned_matchup_orders.setdefault(submission.session_id, set()).update(matchup_orders)
                picked = [engine.game_label(step_specs, step_specs[order]) for order in matchup_orders]
            else:
                picked = [str(session_deck.deck_id) for session_deck in submission.decks.all()]
                self.brought_session_deck_ids[(submission.session_id, submission.step.order, submission.seat)] = [
                    session_deck.id for session_deck in submission.decks.all()]
            self.picks[(submission.session_id, submission.step.order, submission.seat)] = picked

    def headers_for(self, template_id, column_prefix, participant_labels):
        return get_step_headers(
            self.step_specs_by_template_id.get(template_id, []), column_prefix, participant_labels)

    def blank_cells_for(self, template_id):
        return [
            cell
            for spec in self.step_specs_by_template_id.get(template_id, [])
            for cell in self.blank_step_cells(spec)
        ]

    def cells_for(self, session, participant_seats, participant_names_by_seat):
        cells = []
        for spec in self.step_specs_by_template_id.get(session.template_id, []):
            if spec.order >= session.revealed_step_count:
                cells.extend(self.blank_step_cells(spec))
            elif spec.is_submit:
                cells.extend(
                    self.join(self.submitted_deck_ids.get((session.id, seat), []))
                    for seat in participant_seats)
            elif spec.is_play:
                cells.extend(self.play_cells(session, spec, participant_seats, participant_names_by_seat))
            else:
                cells.extend(self.picked_cell(session, spec, seat) for seat in participant_seats)
        return cells

    @staticmethod
    def blank_step_cells(spec):
        return [''] * (PLAY_STEP_COLUMN_COUNT if spec.is_play else PARTICIPANT_COUNT)

    def join(self, values):
        return self.selection_delimiter.join(values)

    def picked_cell(self, session, spec, seat):
        return self.join(self.picks.get((session.id, spec.order, seat), []))

    def plan_for(self, session, spec, result):
        brought_by_seat = {
            seat: session_deck_ids[0]
            for seat in SEATS
            for session_deck_ids in [self.brought_session_deck_ids.get((session.id, spec.order, seat), [])]
            if session_deck_ids
        }
        if set(brought_by_seat) != set(SEATS):
            return None
        report = result.adaptive_report() if result is not None and result.has_adaptive_report else None
        return engine.plan_game(spec, brought_by_seat, self.adaptive_records.get((session.id, spec.order)), report)

    def deck_cell(self, session_deck_id):
        return self.deck_ids_by_session_deck_id.get(session_deck_id, '')

    def play_cells(self, session, spec, participant_seats, participant_names_by_seat):
        result = self.results.get((session.id, spec.order))
        plan = self.plan_for(session, spec, result)
        is_assigned = plan is not None and plan.is_assigned
        if spec.order in self.banned_matchup_orders.get(session.id, ()):
            winner = BANNED_MATCHUP_CELL
        elif result is not None:
            winner = participant_names_by_seat[result.winner_seat]
        else:
            winner = ''
        scores_by_seat = {
            Seat.HOST: result.host_score if result else None,
            Seat.GUEST: result.guest_score if result else None,
        }
        return [
            str(engine.GameType(spec.game_type).label),
            *(self.picked_cell(session, spec, seat) for seat in participant_seats),
            *(self.deck_cell(plan.played_by_seat[seat]) if is_assigned else '' for seat in participant_seats),
            *(plan.chains_for(seat) if is_assigned and plan.chains_for(seat) is not None else ''
              for seat in participant_seats),
            self.deck_cell(plan.first_deck_id) if plan is not None else '',
            winner,
            *('' if scores_by_seat[seat] is None else scores_by_seat[seat] for seat in participant_seats),
        ]
