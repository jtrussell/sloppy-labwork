from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from ghostform.hooks import (
    has_linked_responses, mark_responses_context_removed, update_response_context
)
from .models import MatchResult
from .result_forms import build_result_context, get_result_context_key


@receiver(post_save, sender=MatchResult)
def refresh_result_form_responses(sender, instance, **kwargs):
    context_key = get_result_context_key(instance.match_id)
    if has_linked_responses(context_key):
        update_response_context(context_key, build_result_context(instance))


@receiver(post_delete, sender=MatchResult)
def mark_result_form_responses_removed(sender, instance, **kwargs):
    mark_responses_context_removed(get_result_context_key(instance.match_id))
