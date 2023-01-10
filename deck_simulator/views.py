import json

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from common.auth import teammate_required
from deck_simulator.models import GeneratedDeck
from kftools.decks.generator import DeckGenerator
from kftools.decks.proxy import ProxyGenerator
from kftools.decks.models import GenerationConstraints

deck_generator = DeckGenerator()
proxy_generator = ProxyGenerator()


def _parse_deck_constraints(body):
    parsed = json.loads(body)
    if len(parsed['houses'].keys()) > 3:
        raise ValueError("Invalid predefined cards")
    for cards in parsed['houses'].values():
        if len(cards) > 12:
            raise ValueError("Invalid predefined cards")
    return parsed


@teammate_required
@ensure_csrf_cookie
def deck_simulator(request):
    # if request.method == 'POST':
    #     constraints = _parse_deck_constraints(request.body)
    #     deck = deck_generator.generate_deck(GenerationConstraints.)
    #     proxy = proxy_generator.generate_pdf(deck)
    #     GeneratedDeck.objects.create(uid=deck.id, created_by=request.user, deck_data=deck.to_json())
    #     return HttpResponse(proxy, content_type='application/pdf')
    if request.method == 'POST':
        constraints = _parse_deck_constraints(request.body)
        deck = deck_generator.generate_deck(GenerationConstraints.from_dict({
            'predefined_cards': {
                'ids_by_house': constraints['houses']
            }
        }))
        proxy = proxy_generator.generate_pdf(deck)
        return HttpResponse(proxy, content_type='application/pdf')
    available_cards = sorted(
        ({'name': card.name, 'id': card.id, 'house': card.house} for card in deck_generator.set_data.available_cards),
        key=lambda c: c['name']
    )
    return render(request, 'deck_simulator/deck-simulator.html', {'available_cards': available_cards})


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
