from django.shortcuts import render
from allauth.account.decorators import login_required

from transporter_platform.models import MatchingService, PodPlayer


# @login_required
def kagi_live(request):
    is_checked_in = False
    matched_with = None

    try:
        player = PodPlayer.objects.get(user=request.user)
    except PodPlayer.DoesNotExist:
        player = None

    if not player:
        return render(request, 'transporter_platform/page-kagi-live--no-player.html', {})

    if request.method == 'POST':
        MatchingService.create_request_and_complete_if_able(player)
        is_checked_in = True

    if matched_with:
        return _kagi_live_matched(request, matched_with)
    elif is_checked_in:
        return _kagi_live_check_waiting_for_match(request)
    else:
        return _kagi_live_request_match_form(request)


def _kagi_live_request_match_form(request):
    return render(request, 'transporter_platform/page-kagi-live--request-match.html', {})


def _kagi_live_check_waiting_for_match(request):
    return render(request, 'transporter_platform/page-kagi-live--waiting.html', {})


def _kagi_live_matched(request, matched_with):
    return render(request, 'transporter_platform/page-kagi-live--matched.html', {
        'matched_with': matched_with
    })
