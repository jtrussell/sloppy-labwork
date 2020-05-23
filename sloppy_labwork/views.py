from django.shortcuts import render
from django.middleware.csrf import get_token
from allauth.account.decorators import login_required


def index(request):
    return render(request, 'page-home.html', {})


@login_required
def profile(request):
    return render(request, 'page-profile.html', {
        'csrf_token': get_token(request)
    })
