from django.db.models import Q
from django.utils import timezone

from ghostform.hooks import get_response_form
from ghostform.picker import FORM_PICKER_META_SEPARATOR, build_form_option_for, build_form_picker_context
from .forms import COPY_SOURCE_RESULT_FORM
from .models import Tournament


REPORT_DIALOG_FIELD_ID_FORMAT = 'report-form-%s'
RESULT_FORM_INLINE_ERROR_MESSAGE = 'Please fix the highlighted answers below.'


def get_active_result_form(tournament):
    result_form = tournament.result_form
    if result_form and result_form.get_active_questions().exists():
        return result_form
    return None


def get_result_context_key(match_id):
    return f'tourney-match:{match_id}'


def get_stage_player_display_name(stage_player):
    return stage_player.player.get_display_name() if stage_player else ''


def build_result_context(result):
    match = result.match
    round_obj = match.round
    stage = round_obj.stage
    tournament = stage.tournament
    return [
        ('Tournament', tournament.name),
        ('Tournament code', tournament.code),
        ('Stage', stage.name),
        ('Round', round_obj.order),
        ('Player one', get_stage_player_display_name(match.player_one)),
        ('Player two', get_stage_player_display_name(match.player_two) or 'Bye'),
        ('Winner', get_stage_player_display_name(result.winner) or 'Tie'),
        ('Player one score', result.player_one_score),
        ('Player two score', result.player_two_score),
        ('Result recorded at', timezone.localtime(result.updated_on).strftime('%Y-%m-%d %H:%M:%S')),
    ]


def build_result_response_form(tournament, is_admin, data=None, auto_id=REPORT_DIALOG_FIELD_ID_FORMAT):
    result_form = get_active_result_form(tournament)
    if result_form is None:
        return None
    return get_response_form(result_form, data, all_optional=is_admin, auto_id=auto_id)


def build_report_dialog_context(tournament, is_admin, can_report_results):
    result_form = get_active_result_form(tournament) if can_report_results else None
    return {
        'active_result_form': result_form,
        'report_response_form': get_response_form(
            result_form, all_optional=is_admin,
            auto_id=REPORT_DIALOG_FIELD_ID_FORMAT) if result_form else None,
    }


COPIED_RESULT_FORM_TITLE_SEPARATOR = ' - '


def build_copied_result_form_title(source_tournament, source_result_form, copied_tournament_name):
    source_title_prefix = f'{source_tournament.name}{COPIED_RESULT_FORM_TITLE_SEPARATOR}'
    base_title = source_result_form.title
    if base_title.startswith(source_title_prefix) and len(base_title) > len(source_title_prefix):
        base_title = base_title[len(source_title_prefix):]
    return f'{copied_tournament_name}{COPIED_RESULT_FORM_TITLE_SEPARATOR}{base_title}'


def copy_result_form_for_tournament(source_tournament, copied_tournament, owner):
    source_result_form = source_tournament.result_form
    copied_tournament.result_form = source_result_form.duplicate(
        owner=owner,
        title=build_copied_result_form_title(
            source_tournament, source_result_form, copied_tournament.name),
    )
    copied_tournament.save(update_fields=['result_form'])


def is_result_response_form_valid(response_form):
    return response_form is None or response_form.is_valid()


def get_result_report_error_message(response_form):
    if response_form is not None and response_form.is_bound and response_form.errors:
        return f'Please complete the result form. {response_form.get_error_summary()}'
    return 'Error reporting match result. Please check the form.'


def record_result_response(response_form, user, result, is_admin):
    if response_form is None:
        return None
    if is_admin and not response_form.has_any_answer():
        return None
    return response_form.save_response(
        user,
        context=build_result_context(result),
        context_key=get_result_context_key(result.match_id),
    )


def build_result_form_picker_options(copy_source_result_form, linked_result_form, user):
    picker_options = []
    if linked_result_form is not None and not linked_result_form.can_edit(user):
        linked_option = build_form_option_for(linked_result_form, user)
        picker_options.append({
            **linked_option,
            'meta': FORM_PICKER_META_SEPARATOR.join(['Owned by another admin', linked_option['meta']]),
        })
    if copy_source_result_form is not None:
        picker_options.append({
            'value': COPY_SOURCE_RESULT_FORM,
            'title': f'Copy of {copy_source_result_form.title}',
            'meta': 'New form for this tournament · same questions, no responses',
            'preview_code': copy_source_result_form.code,
        })
    picker_options.append({
        'value': '',
        'title': 'No form',
        'meta': "Players won't be asked any extra questions",
        'preview_code': '',
    })
    return picker_options


def build_result_form_picker_context(tournament_form, user):
    selected_value = tournament_form['result_form'].value()
    selected_value = '' if selected_value is None else str(selected_value)
    selected_form = (
        tournament_form.result_form_queryset.filter(pk=selected_value).first()
        if selected_value.isdigit() else None
    )
    return build_form_picker_context(
        user,
        field_name='result_form',
        selected_value=selected_value,
        special_options=build_result_form_picker_options(
            tournament_form.copy_source_result_form,
            getattr(tournament_form.instance, 'result_form', None),
            user,
        ),
        selected_form=selected_form,
    )


def describe_tournaments_using_forms(ghostforms, viewer):
    tournament_names_by_form_id = {}
    linked_tournaments = Tournament.objects.filter(result_form__in=ghostforms).filter(
        Q(owner=viewer) | Q(tournament_admins__user=viewer)
    ).distinct().order_by('-created_on').values_list('result_form_id', 'name')
    for form_id, tournament_name in linked_tournaments:
        tournament_names_by_form_id.setdefault(form_id, []).append(tournament_name)
    return tournament_names_by_form_id


def user_administers_tournament_using_form(user, ghostform):
    return Tournament.objects.filter(result_form=ghostform).filter(
        Q(owner=user) | Q(tournament_admins__user=user)
    ).exists()
