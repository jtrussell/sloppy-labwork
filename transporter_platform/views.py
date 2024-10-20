from django.shortcuts import render
from allauth.account.decorators import login_required
from .forms import KagiLivePlayForm, ACTION_CREATE, ACTION_CANCEL, ACTION_RECORD_MATCH
from .models import MatchRequest
from django.http import HttpResponseRedirect
from datetime import datetime
from django.utils.safestring import mark_safe

from transporter_platform.models import MatchingService, PodPlayer


@login_required
def kagi_live(request):
    is_checked_in = False
    matched_with = None

    try:
        player = PodPlayer.objects.get(user=request.user)
    except PodPlayer.DoesNotExist:
        player = None

    if not player:
        return render(request, 'transporter_platform/page-kagi-live--no-player.html', {
            'footer_text': mark_safe('<a href="/posts/kagi-live-2024/">&larr; Back to sl dot com</a>')
        })

    try:
        req = MatchRequest.objects.filter(
            player=player).latest()
    except MatchRequest.DoesNotExist:
        req = None

    if request.method == 'POST':
        submitted_form = KagiLivePlayForm(request.POST)
        if submitted_form.is_valid():
            action = submitted_form.cleaned_data['action']
            if action == ACTION_CREATE:
                req = MatchingService.create_request_and_complete_if_able(
                    player)
            elif action == ACTION_CANCEL:
                MatchingService.cancel_request_and_completing(req)
            elif action == ACTION_RECORD_MATCH:
                MatchingService.record_match(
                    req.player, req.completed_by.player)
                MatchingService.cancel_request_and_completing(req)
        return HttpResponseRedirect(request.path_info)

    if req:
        is_checked_in = not req.is_cancelled
        matched_with = req.completed_by

    if matched_with:
        return _kagi_live_matched(request, matched_with)
    elif is_checked_in:
        return _kagi_live_check_waiting_for_match(request, req.created_on)
    else:
        return _kagi_live_request_match_form(request)


def _kagi_live_request_match_form(request):
    form = KagiLivePlayForm(initial={'action': ACTION_CREATE})
    return render(request, 'transporter_platform/page-kagi-live--request-match.html', {
        'form': form
    })


def _kagi_live_check_waiting_for_match(request, created_on):
    form = KagiLivePlayForm(initial={'action': ACTION_CANCEL})

    time_delta = datetime.now(created_on.tzinfo) - created_on
    five_minutes = 5 * 60
    ten_minutes = 10 * 60
    one_hour = 60 * 60
    elapsed_seconds = time_delta.total_seconds()

    if elapsed_seconds > one_hour:
        refresh_after_seconds = 10 * 60
    elif elapsed_seconds > ten_minutes:
        refresh_after_seconds = 5 * 60
    elif elapsed_seconds > five_minutes:
        refresh_after_seconds = 1 * 60
    else:
        refresh_after_seconds = 15

    return render(request, 'transporter_platform/page-kagi-live--waiting.html', {
        'form': form,
        'refresh_after_seconds': refresh_after_seconds,
        'footer_text': MatchingService.get_footer_text()
    })


def _kagi_live_matched(request, matched_with):
    cancel_form = KagiLivePlayForm(initial={'action': ACTION_CANCEL})
    record_form = KagiLivePlayForm(initial={'action': ACTION_RECORD_MATCH})
    return render(request, 'transporter_platform/page-kagi-live--matched.html', {
        'matched_with': matched_with,
        'cancel_form': cancel_form,
        'record_form': record_form
    })
