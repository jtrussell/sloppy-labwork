import json

from django.http import HttpResponse
from django.shortcuts import render

from common.auth import teammate_required
from deck_simulator.models import GeneratedDeck
from kftools.decks.generator import DeckGenerator
from kftools.decks.proxy import ProxyGenerator

deck_generator = DeckGenerator()
proxy_generator = ProxyGenerator()


def _parse_deck_constraints(body):
    parsed = json.loads(body)
    # TODO: validate
    return parsed


@teammate_required
def deck_simulator(request):
    # if request.method == 'POST':
    #     constraints = _parse_deck_constraints(request.body)
    #     deck = deck_generator.generate_deck(GenerationConstraints.)
    #     proxy = proxy_generator.generate_pdf(deck)
    #     GeneratedDeck.objects.create(uid=deck.id, created_by=request.user, deck_data=deck.to_json())
    #     return HttpResponse(proxy, content_type='application/pdf')
    return render(request, 'deck_simulator/deck-simulator.html')


@teammate_required
def proxy(request):
    deck = deck_generator.generate_deck()
    proxy = proxy_generator.generate_pdf(deck)
    # GeneratedDeck.objects.create(uid=deck.id, created_by=request.user, deck_data=deck.to_json())
    return HttpResponse(proxy, content_type='application/pdf')


@teammate_required
def my_decks(request):
    # TODO
    return render(request, 'deck_simulator/my-decks.html')


@teammate_required
def deck_info(request, **kwargs):
    # TODO
    return render(request, 'deck_simulator/deck-info.html')
