from django.shortcuts import render, get_object_or_404
from .models import Deck
from register.models import DeckRegistration


def deck_details(request, id):
    deck = get_object_or_404(Deck, id=id)
    registrations = deck.deck_registrations
    return render(request, 'decks/detail.html', {})
