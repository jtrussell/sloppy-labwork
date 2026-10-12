from .forms import ResponseForm
from .models import (
    FORM_USAGE_DESCRIBERS, RESPONSE_ACCESS_CHECKS, Response, build_response_context
)


DEFAULT_RESPONSE_FORM_PREFIX = 'ghostform'


def register_response_access_check(check):
    if check not in RESPONSE_ACCESS_CHECKS:
        RESPONSE_ACCESS_CHECKS.append(check)


def register_form_usage_describer(describe_usage):
    if describe_usage not in FORM_USAGE_DESCRIBERS:
        FORM_USAGE_DESCRIBERS.append(describe_usage)


def get_response_form(form, data=None, *, questions=None, all_optional=False,
                      prefix=DEFAULT_RESPONSE_FORM_PREFIX, auto_id='id_%s'):
    return ResponseForm(
        data,
        ghostform=form,
        questions=questions,
        all_optional=all_optional,
        prefix=prefix,
        auto_id=auto_id,
    )


def has_linked_responses(context_key):
    return Response.objects.filter(
        context_key=context_key, is_context_removed=False).exists()


def update_response_context(context_key, context):
    return Response.objects.filter(
        context_key=context_key, is_context_removed=False
    ).update(context=build_response_context(context))


def mark_responses_context_removed(context_key):
    return Response.objects.filter(
        context_key=context_key, is_context_removed=False
    ).update(is_context_removed=True)
