from dataclasses import dataclass

from trade_secrets import engine
from trade_secrets.engine import opponent_of

from .match_sessions import get_player_one_seat
from .models import Stage
from .reporting import can_user_edit_match, describe_winner, is_result_locked_for


TIE_WINNER_VALUE = ''
SCORE_SEPARATOR = '–'


class PanelState:
    UNREPORTED = 'unreported'
    REPORTED = 'reported'
    DIFFERS = 'differs'


@dataclass(frozen=True)
class ReportValues:
    winner_id: int = None
    is_tie: bool = False
    player_one_score: int = None
    player_two_score: int = None

    @property
    def has_outcome(self):
        return self.is_tie or self.winner_id is not None

    @property
    def has_scores(self):
        return self.player_one_score is not None and self.player_two_score is not None


@dataclass(frozen=True)
class SessionOutcome:
    recorded_game_count: int
    values: ReportValues


@dataclass(frozen=True)
class ReportPanel:
    state: str
    can_report: bool
    is_locked: bool
    result_summary: str


def does_stage_report_scores(stage):
    return stage.report_full_scores != Stage.SCORE_REPORTING_DISABLED


def is_single_game_session(state):
    return len(engine.play_steps(state.steps)) == 1


def get_counted_results(session, state):
    return [
        result for result in session.results.select_related('step')
        if result.step.order < state.revealed_count and result.step.order not in state.banned_matchup_orders
    ]


def get_session_scores_by_seat(session, state, games_won_by_seat):
    counted_results = get_counted_results(session, state)
    if not counted_results:
        return {}
    if is_single_game_session(state):
        only_result = counted_results[0]
        return {engine.Seat.HOST: only_result.host_score, engine.Seat.GUEST: only_result.guest_score}
    return games_won_by_seat


def summarize_session_outcome(match):
    session = match.trade_secrets_session
    stage = match.round.stage
    state = session.build_engine_state()
    player_one_seat = get_player_one_seat(match)
    player_two_seat = opponent_of(player_one_seat)
    games_won_by_seat = engine.games_won(state)
    player_one_wins = games_won_by_seat[player_one_seat]
    player_two_wins = games_won_by_seat[player_two_seat]
    recorded_game_count = player_one_wins + player_two_wins

    winner_id = None
    if player_one_wins > player_two_wins:
        winner_id = match.player_one_id
    elif player_two_wins > player_one_wins:
        winner_id = match.player_two_id
    is_tie = recorded_game_count > 0 and winner_id is None and stage.are_ties_allowed

    scores_by_seat = get_session_scores_by_seat(session, state, games_won_by_seat) if (
        does_stage_report_scores(stage)) else {}
    return SessionOutcome(
        recorded_game_count=recorded_game_count,
        values=ReportValues(
            winner_id=winner_id,
            is_tie=is_tie,
            player_one_score=scores_by_seat.get(player_one_seat),
            player_two_score=scores_by_seat.get(player_two_seat),
        ),
    )


def get_reported_values(result):
    return ReportValues(
        winner_id=result.winner_id,
        is_tie=result.winner_id is None,
        player_one_score=result.player_one_score,
        player_two_score=result.player_two_score,
    )


def does_result_match_session(result, outcome):
    session_values = outcome.values
    if not session_values.has_outcome:
        return True
    reported_values = get_reported_values(result)
    if (reported_values.winner_id, reported_values.is_tie) != (session_values.winner_id, session_values.is_tie):
        return False
    if reported_values.has_scores and session_values.has_scores:
        return (
            reported_values.player_one_score == session_values.player_one_score
            and reported_values.player_two_score == session_values.player_two_score)
    return True


def describe_result(result):
    outcome_text = 'Tie' if result.winner_id is None else f'{describe_winner(result)} won'
    scores = (result.player_one_score, result.player_two_score)
    if result.winner_id == result.match.player_two_id:
        scores = tuple(reversed(scores))
    if None in scores:
        return outcome_text
    return f'{outcome_text} {scores[0]}{SCORE_SEPARATOR}{scores[1]}'


def get_reported_result(match):
    return getattr(match, 'result', None)


def can_user_report_from_session(match, user):
    if not user.is_authenticated or not can_user_edit_match(match, user):
        return False
    is_admin = match.round.stage.tournament.is_user_admin(user)
    return not is_result_locked_for(match, is_admin)


def is_result_locked_for_viewer(match, user):
    if not user.is_authenticated or not can_user_edit_match(match, user):
        return False
    return is_result_locked_for(match, match.round.stage.tournament.is_user_admin(user))


def build_report_panel(match, user):
    result = get_reported_result(match)
    if result is None:
        state = PanelState.UNREPORTED
    elif does_result_match_session(result, summarize_session_outcome(match)):
        state = PanelState.REPORTED
    else:
        state = PanelState.DIFFERS
    return ReportPanel(
        state=state,
        can_report=can_user_report_from_session(match, user),
        is_locked=is_result_locked_for_viewer(match, user),
        result_summary=describe_result(result) if result else '',
    )


def choose_prefilled_values(match, outcome):
    result = get_reported_result(match)
    if outcome.values.has_outcome or result is None:
        return outcome.values
    return get_reported_values(result)


def describe_prefill_source(match, outcome):
    if outcome.values.has_outcome:
        game_count = outcome.recorded_game_count
        return f'Filled in from this session: {game_count} game{"" if game_count == 1 else "s"} recorded.'
    if get_reported_result(match) is not None:
        return 'Showing the result already reported to the tournament.'
    if outcome.recorded_game_count:
        return 'Games are level in this session, so pick the winner.'
    return 'No games are recorded in this session yet.'


def parse_submitted_values(match, submitted_data):
    def parse_score(field_name):
        raw_score = submitted_data.get(field_name, '')
        return int(raw_score) if raw_score.isdigit() else None

    raw_winner = submitted_data.get('winner')
    winner_id = int(raw_winner) if raw_winner and raw_winner.isdigit() else None
    if winner_id not in (match.player_one_id, match.player_two_id):
        winner_id = None
    return ReportValues(
        winner_id=winner_id,
        is_tie=raw_winner == TIE_WINNER_VALUE,
        player_one_score=parse_score('player_one_score'),
        player_two_score=parse_score('player_two_score'),
    )


def build_player_slots(match, values):
    return [
        {
            'stage_player': stage_player,
            'name': stage_player.player.get_display_name(),
            'is_winner': values.winner_id == stage_player.id,
            'score_field_name': score_field_name,
            'score': score,
        }
        for stage_player, score_field_name, score in (
            (match.player_one, 'player_one_score', values.player_one_score),
            (match.player_two, 'player_two_score', values.player_two_score),
        )
    ]
