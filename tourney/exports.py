import csv

from ghostform.exports import (
    format_export_timestamp, get_question_cells, get_question_headers, make_spreadsheet_safe
)
from ghostform.hooks import find_latest_linked_responses
from ghostform.models import CSV_SELECTION_DELIMITER
from trade_secrets.engine import Seat, opponent_of
from trade_secrets.exports import SessionExporter

from .models import Match
from .result_forms import get_result_context_key


PLAYER_ONE_LABEL = 'Player one'
PLAYER_TWO_LABEL = 'Player two'
PARTICIPANT_LABELS = (PLAYER_ONE_LABEL, PLAYER_TWO_LABEL)
TIE_CELL = 'Tie'
TRADE_SECRETS_COLUMN_PREFIX = 'TS'


def get_export_matches(tournament):
    return list(Match.objects.filter(
        round__stage__tournament=tournament, player_two__isnull=False
    ).select_related(
        'round__stage', 'player_one__player__user', 'player_one__pod',
        'player_two__player__user', 'result__winner__player__user',
        'trade_secrets_session__template',
    ).order_by('round__stage__order', 'round__order', 'created_on', 'id'))


def get_display_name(stage_player):
    return stage_player.player.get_display_name()


def get_winner_cell(match):
    if not match.has_result():
        return ''
    winner = match.result.winner
    return get_display_name(winner) if winner else TIE_CELL


def get_match_cells(match, includes_pod):
    result = match.result if match.has_result() else None
    cells = [match.round.stage.name, match.round.order]
    if includes_pod:
        cells.append(match.player_one.pod.name if match.player_one.pod else '')
    cells.extend([
        get_display_name(match.player_one),
        get_display_name(match.player_two),
        get_winner_cell(match),
        result.player_one_score if result else None,
        result.player_two_score if result else None,
        format_export_timestamp(result.updated_on) if result else '',
    ])
    return cells


def get_match_headers(includes_pod):
    headers = ['Stage', 'Round']
    if includes_pod:
        headers.append('Pod')
    headers.extend([
        PLAYER_ONE_LABEL, PLAYER_TWO_LABEL, 'Winner',
        f'{PLAYER_ONE_LABEL} score', f'{PLAYER_TWO_LABEL} score', 'Result recorded at',
    ])
    return headers


class ResultFormColumns:
    def __init__(self, result_form, matches):
        self.questions = list(result_form.get_questions_for_export()) if result_form else []
        self.responses_by_context_key = find_latest_linked_responses(
            result_form, [get_result_context_key(match.id) for match in matches]
        ) if result_form else {}

    def headers(self):
        return [header for question in self.questions for header in get_question_headers(question)]

    def cells_for(self, match):
        response = self.responses_by_context_key.get(get_result_context_key(match.id))
        answers_by_question_id = {
            answer.question_id: answer for answer in response.answers.all()
        } if response else {}
        return [
            cell
            for question in self.questions
            for cell in get_question_cells(question, answers_by_question_id.get(question.id))
        ]


def get_player_one_seat(match):
    session = match.trade_secrets_session
    if match.player_one.player.user_id == session.guest_id:
        return Seat.GUEST
    return Seat.HOST


class TradeSecretsColumns:
    def __init__(self, tournament, matches):
        self.templates = self.collect_templates(tournament, matches)
        sessions = [match.trade_secrets_session for match in matches if match.trade_secrets_session]
        self.exporter = SessionExporter(
            [template.id for template in self.templates], sessions, CSV_SELECTION_DELIMITER)

    @staticmethod
    def collect_templates(tournament, matches):
        templates_by_id = {}
        if tournament.trade_secrets_template_id is not None:
            templates_by_id[tournament.trade_secrets_template_id] = tournament.trade_secrets_template
        for match in matches:
            session = match.trade_secrets_session
            if session is not None:
                templates_by_id.setdefault(session.template_id, session.template)
        return list(templates_by_id.values())

    def column_prefix_for(self, template):
        if len(self.templates) == 1:
            return TRADE_SECRETS_COLUMN_PREFIX
        return f'{TRADE_SECRETS_COLUMN_PREFIX} [{template.name} {template.code}]'

    def headers(self):
        if not self.templates:
            return []
        headers = [f'{TRADE_SECRETS_COLUMN_PREFIX} session', f'{TRADE_SECRETS_COLUMN_PREFIX} template']
        for template in self.templates:
            headers.extend(self.exporter.headers_for(
                template.id, self.column_prefix_for(template), PARTICIPANT_LABELS))
        return headers

    def cells_for(self, match):
        if not self.templates:
            return []
        session = match.trade_secrets_session
        cells = [session.code, session.template.name] if session else ['', '']
        for template in self.templates:
            if session is not None and session.template_id == template.id:
                cells.extend(self.session_cells_for(match))
            else:
                cells.extend(self.exporter.blank_cells_for(template.id))
        return cells

    def session_cells_for(self, match):
        player_one_seat = get_player_one_seat(match)
        player_two_seat = opponent_of(player_one_seat)
        return self.exporter.cells_for(
            match.trade_secrets_session,
            (player_one_seat, player_two_seat),
            {
                player_one_seat: get_display_name(match.player_one),
                player_two_seat: get_display_name(match.player_two),
            },
        )


def write_matches_csv(tournament, output):
    matches = get_export_matches(tournament)
    includes_pod = any(match.player_one.pod_id for match in matches)
    result_form_columns = ResultFormColumns(tournament.result_form, matches)
    trade_secrets_columns = TradeSecretsColumns(tournament, matches)

    writer = csv.writer(output)
    header = [
        *get_match_headers(includes_pod),
        *result_form_columns.headers(),
        *trade_secrets_columns.headers(),
    ]
    writer.writerow([make_spreadsheet_safe(cell) for cell in header])

    for match in matches:
        row = [
            *get_match_cells(match, includes_pod),
            *result_form_columns.cells_for(match),
            *trade_secrets_columns.cells_for(match),
        ]
        writer.writerow([make_spreadsheet_safe('' if cell is None else cell) for cell in row])
