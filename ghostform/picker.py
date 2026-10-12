from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db.models import Count, Q
from django.urls import reverse

from .models import FORM_USAGE_DESCRIBERS, Form


FORM_PICKER_RESULT_LIMIT = 20
FORM_PICKER_META_SEPARATOR = ' · '


def describe_form_usage(ghostforms, viewer):
    usage_labels_by_form_id = {}
    for describe_usage in FORM_USAGE_DESCRIBERS:
        for form_id, usage_labels in describe_usage(ghostforms, viewer).items():
            usage_labels_by_form_id.setdefault(form_id, []).extend(usage_labels)
    return usage_labels_by_form_id


def format_usage_summary(usage_labels):
    if not usage_labels:
        return 'not linked'
    if len(usage_labels) == 1:
        return f'used by {usage_labels[0]}'
    return f'used by {usage_labels[0]} and {len(usage_labels) - 1} more'


def annotate_picker_stats(ghostforms):
    return ghostforms.annotate(
        question_count=Count(
            'questions', filter=Q(questions__is_archived=False), distinct=True),
        response_count=Count('responses', distinct=True),
    )


def build_form_option(ghostform, usage_labels):
    meta_parts = [
        ghostform.get_status_display(),
        f'{ghostform.question_count} question{"" if ghostform.question_count == 1 else "s"}',
        f'{ghostform.response_count} response{"" if ghostform.response_count == 1 else "s"}',
        format_usage_summary(usage_labels),
        f'edited {naturaltime(ghostform.updated_on)}',
    ]
    return {
        'value': str(ghostform.pk),
        'title': ghostform.title,
        'meta': FORM_PICKER_META_SEPARATOR.join(meta_parts),
        'preview_code': ghostform.code,
    }


def build_form_options(ghostforms, viewer):
    ghostforms = list(ghostforms)
    usage_labels_by_form_id = describe_form_usage(ghostforms, viewer)
    return [
        build_form_option(ghostform, usage_labels_by_form_id.get(ghostform.id, []))
        for ghostform in ghostforms
    ]


def search_pickable_forms(user, query=''):
    owned_forms = Form.objects.filter(owner=user)
    if query:
        owned_forms = owned_forms.filter(title__icontains=query)
    owned_forms = annotate_picker_stats(owned_forms).order_by(
        '-updated_on', '-id')[:FORM_PICKER_RESULT_LIMIT]
    return build_form_options(owned_forms, user)


def build_form_option_for(ghostform, viewer):
    annotated_form = annotate_picker_stats(Form.objects.filter(pk=ghostform.pk)).first()
    return build_form_options([annotated_form], viewer)[0] if annotated_form else None


def build_form_picker_context(user, field_name, selected_value, special_options=(), selected_form=None):
    selected_value = '' if selected_value is None else str(selected_value)
    special_options = list(special_options)
    selected_option = next(
        (option for option in special_options if option['value'] == selected_value), None)
    if selected_option is None and selected_form is not None:
        selected_option = build_form_option_for(selected_form, user)
    if selected_option is None:
        selected_value = ''
        selected_option = next(
            (option for option in special_options if option['value'] == selected_value), None)

    return {
        'field_name': field_name,
        'selected_value': selected_value,
        'selected_option': selected_option,
        'special_options': special_options,
        'results': search_pickable_forms(user),
        'results_url': reverse('ghostform:ghostform-picker-results'),
        'preview_url_template': reverse('ghostform:ghostform-picker-preview', args=['FORM_CODE']),
        'create_url': reverse('ghostform:ghostform-create'),
    }
