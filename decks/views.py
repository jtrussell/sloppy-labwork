from django.shortcuts import render, get_object_or_404
from .models import Deck


def deck_details(request, id):
    deck = get_object_or_404(Deck, id=id)
    return render(request, 'decks/detail.html', {})
