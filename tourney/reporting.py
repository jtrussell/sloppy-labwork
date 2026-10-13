from dataclasses import dataclass

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.db import transaction
from django.db.models import Q

from .forms import MatchResultForm
from .models import Match, MatchResult, StagePlayer, TournamentActionLog
from .result_forms import build_result_response_form, is_result_response_form_valid, record_result_response


TOURNAMENT_CLOSED_MESSAGE = 'This tournament is closed. Match results can no longer be submitted by players.'
MATCH_ALREADY_REPORTED_MESSAGE = 'This match already has a result.'
BYE_CANNOT_BE_REPORTED_MESSAGE = 'Bye results are recorded automatically and cannot be reported.'
NO_ACTIVE_STAGE_MESSAGE = 'No active stage found.'
NO_ACTIVE_ROUND_MESSAGE = 'No active round found. Please create a round first.'
NOT_A_STAGE_PARTICIPANT_MESSAGE = 'You are not a participant in this stage.'
OPPONENT_REQUIRED_MESSAGE = 'Please select an opponent.'
INVALID_OPPONENT_MESSAGE = 'Invalid opponent selected.'
OPPONENT_OUTSIDE_POD_MESSAGE = 'You can only report matches against players in your pod.'
DUPLICATE_MATCH_MESSAGE = 'You already have a match against this opponent in this round.'
WINNER_REQUIRED_MESSAGE = 'Please select a winner.'
TIES_NOT_ALLOWED_MESSAGE = 'Ties are not allowed in this stage.'
INVALID_WINNER_MESSAGE = 'Invalid winner selection.'
INVALID_SCORE_MESSAGE = 'Invalid score entered.'

SELF_REPORTED_WINNER_ME = 'me'
SELF_REPORTED_WINNER_THEM = 'them'
SELF_REPORTED_WINNER_TIE = 'tie'


class ReportError(Exception):
    def __init__(self, error_messages, response_form=None, is_final=False):
        super().__init__('; '.join(error_messages))
        self.error_messages = error_messages
        self.response_form = response_form
        self.is_final = is_final


@dataclass
class ReportOutcome:
    result: MatchResult
    was_update: bool


def get_form_error_messages(form):
    error_messages = []
    for field_name, field_errors in form.errors.items():
        field = form.fields.get(field_name)
        field_label = (field.label if field and field.label else field_name.replace('_', ' ').capitalize())
        for field_error in field_errors:
            error_messages.append(
                field_error if field_name == NON_FIELD_ERRORS else f'{field_label}: {field_error}')
    return error_messages


def is_user_in_match(user, match):
    return any(
        stage_player and stage_player.player.user == user
        for stage_player in (match.player_one, match.player_two)
    )


def can_user_add_match(tournament, user):
    if tournament.is_user_admin(user):
        return True
    current_stage = tournament.get_current_stage()
    return bool(
        current_stage and
        current_stage.get_pairing_strategy().is_self_scheduled() and
        tournament.players.filter(user=user).exists()
    )


def describe_winner(result):
    return result.winner.player.get_display_name() if result.winner else 'Tie'


def report_paired_match_result(match, user, result_data):
    tournament = match.round.stage.tournament
    is_admin = tournament.is_user_admin(user)

    if not (is_admin or is_user_in_match(user, match)):
        raise PermissionDenied
    if tournament.is_closed and not is_admin:
        raise ReportError([TOURNAMENT_CLOSED_MESSAGE], is_final=True)
    if match.has_result() and not is_admin:
        raise ReportError([MATCH_ALREADY_REPORTED_MESSAGE], is_final=True)
    if match.is_bye():
        raise ReportError([BYE_CANNOT_BE_REPORTED_MESSAGE])

    form = MatchResultForm(result_data, match=match)
    response_form = build_result_response_form(tournament, is_admin, result_data)
    is_result_valid = form.is_valid()
    is_response_valid = is_result_response_form_valid(response_form)
    if not (is_result_valid and is_response_valid):
        raise ReportError(get_form_error_messages(form), response_form)

    with transaction.atomic():
        existing_result = getattr(match, 'result', None)
        if existing_result:
            result = form.save(commit=False)
            existing_result.winner = result.winner
            existing_result.player_one_score = result.player_one_score
            existing_result.player_two_score = result.player_two_score
            existing_result.save()
            result = existing_result
        else:
            result = form.save(commit=False)
            result.match = match
            result.save()

        record_result_response(response_form, user, result, is_admin)

        action_type = (TournamentActionLog.ActionType.REPORT_RESULT if not existing_result
                       else TournamentActionLog.ActionType.UPDATE_RESULT)
        TournamentActionLog.objects.create(
            tournament=tournament,
            user=user,
            action_type=action_type,
            description=f'Match result {"updated" if existing_result else "reported"}: {describe_winner(result)}'
        )

    return ReportOutcome(result=result, was_update=bool(existing_result))


def parse_self_reported_score(raw_score):
    if not raw_score:
        return None
    try:
        score = int(raw_score)
    except (ValueError, TypeError):
        raise ReportError([INVALID_SCORE_MESSAGE])
    if score < 0:
        raise ReportError([INVALID_SCORE_MESSAGE])
    return score


def find_self_reported_winner(winner_choice, stage, reporter, opponent):
    if not winner_choice:
        raise ReportError([WINNER_REQUIRED_MESSAGE])
    if winner_choice == SELF_REPORTED_WINNER_ME:
        return reporter
    if winner_choice == SELF_REPORTED_WINNER_THEM:
        return opponent
    if winner_choice == SELF_REPORTED_WINNER_TIE:
        if not stage.are_ties_allowed:
            raise ReportError([TIES_NOT_ALLOWED_MESSAGE])
        return None
    raise ReportError([INVALID_WINNER_MESSAGE])


def report_self_scheduled_match_result(tournament, user, result_data):
    if not can_user_add_match(tournament, user):
        raise PermissionDenied
    if tournament.is_closed:
        raise ReportError([TOURNAMENT_CLOSED_MESSAGE])

    current_stage = tournament.get_current_stage()
    if not current_stage:
        raise ReportError([NO_ACTIVE_STAGE_MESSAGE])

    current_round = current_stage.get_current_round()
    if not current_round:
        raise ReportError([NO_ACTIVE_ROUND_MESSAGE])

    reporter = current_stage.stage_players.filter(player__user=user).first()
    if not reporter:
        raise ReportError([NOT_A_STAGE_PARTICIPANT_MESSAGE])

    opponent_id = result_data.get('opponent')
    if not opponent_id:
        raise ReportError([OPPONENT_REQUIRED_MESSAGE])

    try:
        opponent = current_stage.stage_players.get(id=opponent_id)
    except StagePlayer.DoesNotExist:
        raise ReportError([INVALID_OPPONENT_MESSAGE])

    if not reporter.is_in_same_pod_as(opponent):
        raise ReportError([OPPONENT_OUTSIDE_POD_MESSAGE])

    has_existing_match = current_round.matches.filter(
        Q(player_one=reporter, player_two=opponent) |
        Q(player_one=opponent, player_two=reporter)
    ).exists()
    if has_existing_match:
        raise ReportError([DUPLICATE_MATCH_MESSAGE])

    winner = find_self_reported_winner(result_data.get('winner'), current_stage, reporter, opponent)

    player_one_score = None
    player_two_score = None
    if current_stage.report_full_scores > 0:
        player_one_score = parse_self_reported_score(result_data.get('my_score', '').strip())
        player_two_score = parse_self_reported_score(result_data.get('their_score', '').strip())

    is_reporter_admin = tournament.is_user_admin(user)
    response_form = build_result_response_form(tournament, is_reporter_admin, result_data)
    if not is_result_response_form_valid(response_form):
        raise ReportError([], response_form)

    with transaction.atomic():
        match = Match.objects.create(
            round=current_round,
            player_one=reporter,
            player_two=opponent
        )
        result = MatchResult.objects.create(
            match=match,
            winner=winner,
            player_one_score=player_one_score,
            player_two_score=player_two_score
        )
        record_result_response(response_form, user, result, is_reporter_admin)
        TournamentActionLog.objects.create(
            tournament=tournament,
            user=user,
            action_type=TournamentActionLog.ActionType.CREATE_ROUND,
            description=f'Player reported match result: {reporter.player.get_display_name()} vs {opponent.player.get_display_name()} in {current_round.stage.name} Round {current_round.order}'
        )

    return ReportOutcome(result=result, was_update=False)
