from django.shortcuts import render
from .models import Deck

# Create your views here.


def deck_details(request, id):
    return render(request, 'decks/detail.html', {})
