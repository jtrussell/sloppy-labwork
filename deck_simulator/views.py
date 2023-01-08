import json

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from common.auth import teammate_required
from common.utils import partition
from deck_simulator.models import GeneratedDeck
from kftools.decks.models import GeneratedDeck as GeneratedDeckData
from kftools.decks.generator import DeckGenerator
from kftools.decks.proxy import ProxyGenerator
from kftools.decks.models import GenerationConstraints, MinCounts

deck_generator = DeckGenerator()
proxy_generator = ProxyGenerator()


def _parse_deck_constraints(body):
    parsed = json.loads(body)
    if len(parsed['predefined'].keys()) > 3:
        raise ValueError("Invalid predefined cards")
    for cards in parsed['predefined'].values():
        if len(cards) > 12:
            raise ValueError("Invalid predefined cards")
    if not parsed["name"]:
        raise ValueError("name is required")
    return parsed


def _card_listing_data(cards):
    return sorted(
        (card.to_dict() for card in cards),
        key=lambda c: c['name']
    )


@teammate_required
@ensure_csrf_cookie
def deck_simulator(request):
    if request.method == 'POST':
        constraints = _parse_deck_constraints(request.body)
        deck = deck_generator.generate_deck(GenerationConstraints.from_dict({
            'predefined_cards': {
                'ids_by_house': constraints['predefined'],
                'token_id': constraints.get('token')
            },
            'min_counts': MinCounts.from_dict(constraints['meta'])
        }))
        GeneratedDeck.objects.create(uid=deck.id, name=constraints['name'], created_by=request.user, deck_data=deck.to_json())
        return HttpResponse(json.dumps({'id': deck.id}),
                            content_type='application/json')
    available_tokens, available_cards = partition(
        deck_generator.predefinable_cards,
        lambda card: card.type == "token creature"
    )
    available_houses = sorted(deck_generator.available_houses)
    available_count_constraints = deck_generator.available_count_constraints
    available_tags = sorted(deck_generator.available_tags)
    return render(request, 'deck_simulator/deck-simulator.html', {
        'available_cards': _card_listing_data(available_cards),
        'available_tokens': _card_listing_data(available_tokens),
        'available_houses': available_houses,
        'available_tags': available_tags,
        'available_count_constraints': available_count_constraints
    })


@teammate_required
def proxy(request, **params):
    deck_id = params['id']
    deck = GeneratedDeck.objects.get(uid=deck_id)
    proxy = proxy_generator.generate_pdf(GeneratedDeckData.from_json(deck.deck_data))
    return HttpResponse(proxy, content_type='application/pdf')


@teammate_required
def my_decks(request):
    decks = GeneratedDeck.objects.filter(created_by=request.user).order_by('uid')
    paginator = Paginator(decks, 5)

    page_number = request.GET.get('page') or 1
    page_obj = paginator.get_page(page_number)
    return render(request, 'deck_simulator/my-decks.html', {
        'page_obj': page_obj
    })


@teammate_required
def deck_info(request, **params):
    deck_id = params['id']
    deck = GeneratedDeck.objects.get(uid=deck_id)
    return render(request, 'deck_simulator/deck-info.html', {
        'deck': deck
    })
