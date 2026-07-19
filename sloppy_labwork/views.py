from django.shortcuts import render
import random


def birdie():
    """
    Spits out a random birdie based on science.
    """
    return random.choices(
        ["🦆", "🦉", "🦜", "🐧", "🦩", "🦄"],
        [80, 8, 5, 4, 3, 1]
    )[0]


def birdie_or_moose():
    """
    Spits out a random birdie or moose based on science.
    """
    return random.choices(
        [birdie(), "🫎"],
        [4, 6]
    )[0]


def index(request):
    return render(request, 'page-home.html', {})


def contact(request):
    return render(request, 'page-contact.html', {})


def the_team(request):
    return render(request, 'page-team.html', {
        'bhawk': birdie(),
        'crusader': birdie(),
        'jdg314': birdie(),
        'jtrussell': birdie(),
        'kveld': birdie(),
        'miggy9001': birdie(),
        'moosemandude': birdie_or_moose(),
        'not2night': birdie(),
        'nowinstereo': birdie(),
        'quickdraw3457': birdie(),
        'strussell': birdie(),
    })


def styles_demo(request):
    return render(request, 'styles-demo.html', {})