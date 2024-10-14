from django.shortcuts import render
from allauth.account.decorators import login_required
from .forms import KagiLivePlayForm, ACTION_CREATE, ACTION_CANCEL, ACTION_RECORD_MATCH
from .models import MatchRequest

from transporter_platform.models import MatchingService, PodPlayer


@login_required
def kagi_live(request):
    is_checked_in = False
    matched_with = None

    try:
        player = PodPlayer.objects.get(user=request.user)
        req = MatchRequest.objects.filter(player=player).latest()
    except PodPlayer.DoesNotExist:
        player = None
        req = None

    if not player:
        return render(request, 'transporter_platform/page-kagi-live--no-player.html', {})

    if request.method == 'POST':
        submitted_form = KagiLivePlayForm(request.POST)
        if submitted_form.is_valid():
            action = submitted_form.cleaned_data['action']
            if action == ACTION_CREATE:
                req = MatchingService.create_request_and_complete_if_able(
                    player)
            elif action == ACTION_CANCEL:
                req = MatchingService.cancel_request_and_completing(req)
            elif action == ACTION_RECORD_MATCH:
                pass

    if req:
        is_checked_in = not req.is_cancelled
        matched_with = req.completed_by

    if matched_with:
        return _kagi_live_matched(request, matched_with)
    elif is_checked_in:
        return _kagi_live_check_waiting_for_match(request)
    else:
        return _kagi_live_request_match_form(request)


def _kagi_live_request_match_form(request):
    form = KagiLivePlayForm(initial={'action': ACTION_CREATE})
    return render(request, 'transporter_platform/page-kagi-live--request-match.html', {
        'form': form
    })


def _kagi_live_check_waiting_for_match(request):
    form = KagiLivePlayForm(initial={'action': ACTION_CANCEL})
    return render(request, 'transporter_platform/page-kagi-live--waiting.html', {
        'form': form
    })


def _kagi_live_matched(request, matched_with):
    return render(request, 'transporter_platform/page-kagi-live--matched.html', {
        'matched_with': matched_with
    })
