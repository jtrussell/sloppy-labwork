from django.shortcuts import render
from allauth.account.decorators import login_required


# @login_required
def kagi_live(request):
    is_checked_in = True
    matched_with = 'The Villain'

    if matched_with:
        return _kagi_live_matched(request, matched_with)
    elif is_checked_in:
        return _kagi_live_check_waiting_for_match(request)
    else:
        return _kagi_live_check_in(request)


def _kagi_live_check_in(request):
    return render(request, 'transporter_platform/page-kagi-live--check-in.html', {})


def _kagi_live_check_waiting_for_match(request):
    return render(request, 'transporter_platform/page-kagi-live--waiting.html', {})


def _kagi_live_matched(request, matched_with):
    return render(request, 'transporter_platform/page-kagi-live--matched.html', {
        'matched_with': matched_with
    })
