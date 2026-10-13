from django.core.exceptions import PermissionDenied
from django.db.models import Q
from ghostform.hooks import DEFAULT_RESPONSE_FORM_PREFIX
from ghostform.models import Question, TEXT_ANSWER_MAX_LENGTH
from tourney.models import Match, Player, Stage, Tournament
from tourney.reporting import (
    ReportError,
    report_paired_match_result,
    report_self_scheduled_match_result,
    BYE_CANNOT_BE_REPORTED_MESSAGE,
    MATCH_ALREADY_REPORTED_MESSAGE,
    NO_ACTIVE_ROUND_MESSAGE,
    NO_ACTIVE_STAGE_MESSAGE,
    NOT_A_STAGE_PARTICIPANT_MESSAGE,
    SELF_REPORTED_WINNER_ME,
    SELF_REPORTED_WINNER_THEM,
    SELF_REPORTED_WINNER_TIE,
)
from tourney.result_forms import get_active_result_form, get_result_report_error_message
from ..accounts import account_not_linked_message, get_site_user_for_discord_id
from ..interactions import CUSTOM_ID_SEPARATOR
from ..links import absolute_url
from ..registry import Command, COMMAND_TYPE_CHAT_INPUT, OPTION_TYPE_SUB_COMMAND, OPTION_TYPE_STRING, choice
from ..responses import (
    message,
    ephemeral_message,
    modal,
    autocomplete_choices,
    action_row,
    button,
    link_button,
    label,
    text_input,
    radio_group,
    radio_option,
    checkbox,
    string_select,
    select_option,
)
from ..text import truncate

COMMAND_NAME = 'tourney'
SUBCOMMAND_REPORT = 'report'
OPTION_TOURNAMENT = 'tournament'

REPORT_PAIRED_MATCH_ACTION = 'report-match'
REPORT_SELF_SCHEDULED_ACTION = 'report-add'
RETRY_REPORT_ACTION = 'retry'

FIELD_WINNER = 'winner'
FIELD_OPPONENT = 'opponent'
FIELD_PLAYER_ONE_SCORE = 'player_one_score'
FIELD_PLAYER_TWO_SCORE = 'player_two_score'
FIELD_MY_SCORE = 'my_score'
FIELD_THEIR_SCORE = 'their_score'
PAIRED_WINNER_TIE = 'tie'
GHOSTFORM_FIELD_PREFIX = f'{DEFAULT_RESPONSE_FORM_PREFIX}-'

MAX_CHOICES = 25
MAX_CHOICE_NAME_LENGTH = 100
MAX_MODAL_COMPONENTS = 5
MAX_MODAL_TITLE_LENGTH = 45
MAX_LABEL_LENGTH = 45
MAX_LABEL_DESCRIPTION_LENGTH = 100
MAX_SELECT_OPTIONS = 25
MAX_SELECT_OPTION_LABEL_LENGTH = 100
MAX_SCORE_LENGTH = 4
DECK_LINK_PLACEHOLDER = 'https://decksofkeyforge.com/decks/...'

NO_OPEN_TOURNAMENTS_MESSAGE = 'You aren\'t an active player in any open tournaments.'
CHOOSE_TOURNAMENT_MESSAGE = 'You\'re playing in more than one open tournament. Pick one with the `tournament` option.'
TOURNAMENT_NOT_FOUND_MESSAGE = 'I couldn\'t find an open tournament you\'re playing in by that name.'
NO_MATCH_MESSAGE = 'You don\'t have a match in the current round.'
NO_OPPONENTS_MESSAGE = 'There\'s no one left in your pod to report a match against this round.'
MATCH_NOT_FOUND_MESSAGE = 'I couldn\'t find that match anymore.'
NOT_ALLOWED_MESSAGE = 'You aren\'t allowed to report that match.'
REPORT_FAILED_INTRO = 'I couldn\'t save that result:'
TOO_BIG_FOR_DISCORD_MESSAGE = 'This report has more questions than fit in Discord. Please report it on Sloppy Labwork instead.'
REPORT_ON_SITE_LABEL = 'Report on Sloppy Labwork'
TRY_AGAIN_LABEL = 'Try again'
WHO_WON_LABEL = 'Who won?'
OPPONENT_LABEL = 'Opponent'

HELP_TEXT = (
    'Your Discord account must be linked to your Sloppy Labwork account. '
    'Results are posted in the channel once they\'re saved. '
    'If a tournament asks more questions than fit in a Discord form, I\'ll link you to the site instead.'
)

definition = {
    'name': COMMAND_NAME,
    'type': COMMAND_TYPE_CHAT_INPUT,
    'description': 'Take part in Sloppy Labwork tournaments',
    'options': [
        {
            'name': SUBCOMMAND_REPORT,
            'description': 'Report the result of your match',
            'type': OPTION_TYPE_SUB_COMMAND,
            'options': [
                {
                    'name': OPTION_TOURNAMENT,
                    'description': 'Tournament (needed only if you\'re in more than one)',
                    'type': OPTION_TYPE_STRING,
                    'required': False,
                    'autocomplete': True,
                },
            ],
        },
    ],
}


def build_custom_id(action, key):
    return CUSTOM_ID_SEPARATOR.join([COMMAND_NAME, action, str(key)])


def parse_custom_id(custom_id):
    _, action, key = custom_id.split(CUSTOM_ID_SEPARATOR, 2)
    return action, key


def get_display_name(stage_player):
    return stage_player.player.get_display_name()


def find_reportable_tournaments(user):
    return Tournament.objects.filter(
        players__user=user,
        players__status=Player.PlayerStatus.ACTIVE,
        is_closed=False,
    ).distinct().order_by('-created_on')


def report_on_site_response(tournament):
    matches_url = absolute_url('tourney:tourney-detail-matches', tournament.code)
    return ephemeral_message(
        TOO_BIG_FOR_DISCORD_MESSAGE, [action_row(link_button(matches_url, REPORT_ON_SITE_LABEL))])


def wrap_in_label(text, component, description=''):
    if not description and len(text) > MAX_LABEL_LENGTH:
        description = text
    return label(
        truncate(text, MAX_LABEL_LENGTH),
        component,
        description=truncate(description, MAX_LABEL_DESCRIPTION_LENGTH) if description else None,
    )


def build_question_input(question, custom_id, is_required):
    answer_type = question.answer_type
    if answer_type == Question.AnswerType.CHECKBOX:
        return checkbox(custom_id)
    if answer_type == Question.AnswerType.MULTIPLE_CHOICE:
        if len(question.choices) > MAX_SELECT_OPTIONS:
            return None
        options = [
            select_option(truncate(choice_text, MAX_SELECT_OPTION_LABEL_LENGTH), str(index))
            for index, choice_text in enumerate(question.choices)
        ]
        return string_select(custom_id, options, required=is_required)
    if answer_type == Question.AnswerType.DECK_LINK:
        return text_input(custom_id, required=is_required, max_length=TEXT_ANSWER_MAX_LENGTH,
                          placeholder=DECK_LINK_PLACEHOLDER)
    return text_input(custom_id, required=is_required, max_length=TEXT_ANSWER_MAX_LENGTH)


def build_question_components(tournament, user):
    result_form = get_active_result_form(tournament)
    if result_form is None:
        return []
    is_admin = tournament.is_user_admin(user)
    components = []
    for question in result_form.get_active_questions():
        question_input = build_question_input(
            question,
            GHOSTFORM_FIELD_PREFIX + question.get_field_name(),
            question.is_required and not is_admin,
        )
        if question_input is None:
            return None
        components.append(wrap_in_label(question.label, question_input, question.description))
    return components


def build_score_components(stage, first_field, first_label, second_field, second_label):
    if stage.report_full_scores == Stage.SCORE_REPORTING_DISABLED:
        return []
    is_required = stage.report_full_scores == Stage.SCORE_REPORTING_REQUIRED
    return [
        wrap_in_label(first_label, text_input(first_field, required=is_required, max_length=MAX_SCORE_LENGTH)),
        wrap_in_label(second_label, text_input(second_field, required=is_required, max_length=MAX_SCORE_LENGTH)),
    ]


def build_report_modal(tournament, user, custom_id, result_components):
    question_components = build_question_components(tournament, user)
    if question_components is None:
        return report_on_site_response(tournament)
    components = result_components + question_components
    if len(components) > MAX_MODAL_COMPONENTS:
        return report_on_site_response(tournament)
    title = truncate(f'Report · {tournament.name}', MAX_MODAL_TITLE_LENGTH)
    return modal(custom_id, title, components)


def build_paired_report_modal(match, user):
    if match.is_bye():
        return ephemeral_message(BYE_CANNOT_BE_REPORTED_MESSAGE)
    if match.has_result():
        return ephemeral_message(MATCH_ALREADY_REPORTED_MESSAGE)
    stage = match.round.stage
    player_one_name = get_display_name(match.player_one)
    player_two_name = get_display_name(match.player_two)
    winner_options = [
        radio_option(truncate(player_one_name, MAX_SELECT_OPTION_LABEL_LENGTH), str(match.player_one_id)),
        radio_option(truncate(player_two_name, MAX_SELECT_OPTION_LABEL_LENGTH), str(match.player_two_id)),
    ]
    if stage.are_ties_allowed:
        winner_options.append(radio_option('Tie', PAIRED_WINNER_TIE))
    result_components = [wrap_in_label(WHO_WON_LABEL, radio_group(FIELD_WINNER, winner_options))]
    result_components += build_score_components(
        stage,
        FIELD_PLAYER_ONE_SCORE, f'{player_one_name}\'s score',
        FIELD_PLAYER_TWO_SCORE, f'{player_two_name}\'s score',
    )
    return build_report_modal(
        stage.tournament, user, build_custom_id(REPORT_PAIRED_MATCH_ACTION, match.id), result_components)


def find_available_opponents(stage, current_round, reporter):
    already_played_ids = set()
    for played_match in current_round.matches.filter(Q(player_one=reporter) | Q(player_two=reporter)):
        already_played_ids.update([played_match.player_one_id, played_match.player_two_id])
    candidates = stage.stage_players.filter(
        player__status=Player.PlayerStatus.ACTIVE
    ).exclude(id=reporter.id).exclude(id__in=already_played_ids).select_related('player__user')
    return [candidate for candidate in candidates if reporter.is_in_same_pod_as(candidate)]


def build_self_scheduled_report_modal(tournament, stage, current_round, reporter, user):
    opponents = find_available_opponents(stage, current_round, reporter)
    if not opponents:
        return ephemeral_message(NO_OPPONENTS_MESSAGE)
    if len(opponents) > MAX_SELECT_OPTIONS:
        return report_on_site_response(tournament)
    opponent_options = [
        select_option(truncate(get_display_name(opponent), MAX_SELECT_OPTION_LABEL_LENGTH), str(opponent.id))
        for opponent in opponents
    ]
    winner_options = [
        radio_option('I won', SELF_REPORTED_WINNER_ME),
        radio_option('My opponent won', SELF_REPORTED_WINNER_THEM),
    ]
    if stage.are_ties_allowed:
        winner_options.append(radio_option('Tie', SELF_REPORTED_WINNER_TIE))
    result_components = [
        wrap_in_label(OPPONENT_LABEL, string_select(FIELD_OPPONENT, opponent_options, required=True)),
        wrap_in_label(WHO_WON_LABEL, radio_group(FIELD_WINNER, winner_options)),
    ]
    result_components += build_score_components(
        stage, FIELD_MY_SCORE, 'Your score', FIELD_THEIR_SCORE, 'Your opponent\'s score')
    return build_report_modal(
        tournament, user, build_custom_id(REPORT_SELF_SCHEDULED_ACTION, tournament.code), result_components)


def open_report(tournament, user):
    stage = tournament.get_current_stage()
    if not stage:
        return ephemeral_message(NO_ACTIVE_STAGE_MESSAGE)
    current_round = stage.get_current_round()
    if not current_round:
        return ephemeral_message(NO_ACTIVE_ROUND_MESSAGE)
    reporter = stage.stage_players.filter(player__user=user).first()
    if not reporter:
        return ephemeral_message(NOT_A_STAGE_PARTICIPANT_MESSAGE)
    if stage.get_pairing_strategy().is_self_scheduled():
        return build_self_scheduled_report_modal(tournament, stage, current_round, reporter, user)
    match = current_round.matches.filter(Q(player_one=reporter) | Q(player_two=reporter)).first()
    if match is None:
        return ephemeral_message(NO_MATCH_MESSAGE)
    return build_paired_report_modal(match, user)


def choose_tournament(user, tournament_value):
    tournaments = find_reportable_tournaments(user)
    if tournament_value:
        tournament = (tournaments.filter(code=tournament_value).first()
                      or tournaments.filter(name__iexact=tournament_value).first())
        return tournament, None if tournament else TOURNAMENT_NOT_FOUND_MESSAGE
    candidates = list(tournaments[:2])
    if not candidates:
        return None, NO_OPEN_TOURNAMENTS_MESSAGE
    if len(candidates) > 1:
        return None, CHOOSE_TOURNAMENT_MESSAGE
    return candidates[0], None


def handle(interaction):
    user = get_site_user_for_discord_id(interaction.user_id)
    if not user.is_authenticated:
        return ephemeral_message(account_not_linked_message())
    tournament, problem = choose_tournament(user, interaction.option(OPTION_TOURNAMENT))
    if tournament is None:
        return ephemeral_message(problem)
    return open_report(tournament, user)


def autocomplete(interaction):
    user = get_site_user_for_discord_id(interaction.user_id)
    if not user.is_authenticated:
        return autocomplete_choices([])
    query = (interaction.focused_option or {}).get('value', '')
    tournaments = find_reportable_tournaments(user).filter(name__icontains=query)[:MAX_CHOICES]
    return autocomplete_choices([
        choice(truncate(tournament.name, MAX_CHOICE_NAME_LENGTH), tournament.code)
        for tournament in tournaments
    ])


def handle_retry(interaction):
    user = get_site_user_for_discord_id(interaction.user_id)
    if not user.is_authenticated:
        return ephemeral_message(account_not_linked_message())
    _, tournament_code = parse_custom_id(interaction.custom_id)
    tournament = find_reportable_tournaments(user).filter(code=tournament_code).first()
    if tournament is None:
        return ephemeral_message(NO_OPEN_TOURNAMENTS_MESSAGE)
    return open_report(tournament, user)


def find_choice_by_index(question, submitted_indexes):
    if not submitted_indexes:
        return ''
    index = submitted_indexes[0]
    if not index.isdigit() or int(index) >= len(question.choices):
        return ''
    return question.choices[int(index)]


def build_question_answers(tournament, submitted_values):
    result_form = get_active_result_form(tournament)
    if result_form is None:
        return {}
    answers = {}
    for question in result_form.get_active_questions():
        field_key = GHOSTFORM_FIELD_PREFIX + question.get_field_name()
        submitted_value = submitted_values.get(field_key)
        if question.answer_type == Question.AnswerType.MULTIPLE_CHOICE:
            answers[field_key] = find_choice_by_index(question, submitted_value)
        elif question.answer_type == Question.AnswerType.CHECKBOX:
            if submitted_value:
                answers[field_key] = 'on'
        else:
            answers[field_key] = submitted_value or ''
    return answers


def build_paired_result_data(submitted_values):
    winner = submitted_values.get(FIELD_WINNER) or PAIRED_WINNER_TIE
    return {
        'winner': '' if winner == PAIRED_WINNER_TIE else winner,
        'player_one_score': submitted_values.get(FIELD_PLAYER_ONE_SCORE) or '',
        'player_two_score': submitted_values.get(FIELD_PLAYER_TWO_SCORE) or '',
    }


def build_self_scheduled_result_data(submitted_values):
    opponent_ids = submitted_values.get(FIELD_OPPONENT) or []
    return {
        'opponent': opponent_ids[0] if opponent_ids else '',
        'winner': submitted_values.get(FIELD_WINNER) or '',
        'my_score': submitted_values.get(FIELD_MY_SCORE) or '',
        'their_score': submitted_values.get(FIELD_THEIR_SCORE) or '',
    }


def format_score(first_score, second_score):
    if first_score is None or second_score is None:
        return ''
    return f' {first_score}–{second_score}'


def describe_match_outcome(result):
    match = result.match
    player_one_name = get_display_name(match.player_one)
    player_two_name = get_display_name(match.player_two)
    if result.winner_id is None:
        return f'{player_one_name} and {player_two_name} tied' + format_score(
            result.player_one_score, result.player_two_score)
    if result.winner_id == match.player_one_id:
        return f'{player_one_name} beat {player_two_name}' + format_score(
            result.player_one_score, result.player_two_score)
    return f'{player_two_name} beat {player_one_name}' + format_score(
        result.player_two_score, result.player_one_score)


def describe_reported_result(result):
    current_round = result.match.round
    stage = current_round.stage
    context = [f'**{stage.tournament.name}**', stage.name, f'Round {current_round.order}']
    pod = result.match.player_one.pod if stage.has_pods() else None
    if pod:
        context.append(pod.name)
    return ' · '.join(context) + ' — ' + describe_match_outcome(result)


def rejected_report_response(report_error, tournament):
    error_messages = list(report_error.error_messages)
    response_form = report_error.response_form
    if response_form is not None and response_form.is_bound and response_form.errors:
        error_messages.append(get_result_report_error_message(response_form))
    content = '\n'.join([REPORT_FAILED_INTRO] + [f'• {error_message}' for error_message in error_messages])
    if report_error.is_final:
        return ephemeral_message(content)
    retry_button = button(build_custom_id(RETRY_REPORT_ACTION, tournament.code), TRY_AGAIN_LABEL)
    return ephemeral_message(content, [action_row(retry_button)])


def save_report(tournament, report_result, *report_arguments):
    try:
        outcome = report_result(*report_arguments)
    except PermissionDenied:
        return ephemeral_message(NOT_ALLOWED_MESSAGE)
    except ReportError as report_error:
        return rejected_report_response(report_error, tournament)
    return message(describe_reported_result(outcome.result))


def submit_paired_report(match_id, user, submitted_values):
    match = Match.objects.select_related('round__stage__tournament').filter(id=match_id).first()
    if match is None:
        return ephemeral_message(MATCH_NOT_FOUND_MESSAGE)
    tournament = match.round.stage.tournament
    result_data = {
        **build_paired_result_data(submitted_values),
        **build_question_answers(tournament, submitted_values),
    }
    return save_report(tournament, report_paired_match_result, match, user, result_data)


def submit_self_scheduled_report(tournament_code, user, submitted_values):
    tournament = Tournament.objects.filter(code=tournament_code).first()
    if tournament is None:
        return ephemeral_message(TOURNAMENT_NOT_FOUND_MESSAGE)
    result_data = {
        **build_self_scheduled_result_data(submitted_values),
        **build_question_answers(tournament, submitted_values),
    }
    return save_report(tournament, report_self_scheduled_match_result, tournament, user, result_data)


SUBMISSION_HANDLERS = {
    REPORT_PAIRED_MATCH_ACTION: submit_paired_report,
    REPORT_SELF_SCHEDULED_ACTION: submit_self_scheduled_report,
}


def handle_modal_submit(interaction):
    user = get_site_user_for_discord_id(interaction.user_id)
    if not user.is_authenticated:
        return ephemeral_message(account_not_linked_message())
    action, key = parse_custom_id(interaction.custom_id)
    return SUBMISSION_HANDLERS[action](key, user, interaction.submitted_values)


command = Command(
    definition,
    handle,
    autocomplete=autocomplete,
    component=handle_retry,
    modal=handle_modal_submit,
    help_text=HELP_TEXT,
)
