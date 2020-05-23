from django.shortcuts import render
from allauth.account.decorators import login_required


def index(request):
    return render(request, 'register/page-home.html', {})


@login_required
def add(request):
    return render(request, 'register/page-new.html', {})


@login_required
def edit(request):
    return render(request, 'regiseter/page-new.html', {})
