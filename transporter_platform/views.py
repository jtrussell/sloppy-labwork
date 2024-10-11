from django.shortcuts import render
from allauth.account.decorators import login_required


@login_required
def kagi_live(request):
    return render(request, 'transporter_platform/kagi_live.html', {})
