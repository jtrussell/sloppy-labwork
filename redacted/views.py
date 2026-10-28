from random import randrange
from django.shortcuts import render
from requests import post
from .forms import RandomDecksFromDokForm
from .models import FallbackCollection
from decks.models import Set

DOK_PAGE_SIZE = 20

EMPTY_FILTERS_PAYLOAD = {
    'cards': [],
    'completedAuctions': False,
    'constraints': [],
    'excludeHouses': [],
    'expansions': [],
    'forAuction': False,
    'forTrade': False,
    'houses': [],
    'myFavorites': False,
    'notForSale': False,
    'notTags': [],
    'notes': '',
    'notesUser': '',
    'owner': '',
    'owners': [],
    'page': 0,
    'pageSize': DOK_PAGE_SIZE,
    'previousOwner': '',
    'sort': 'SAS_RATING',
    'sortDirection': 'DESC',
    'tags': [],
    'teamDecks': False,
    'title': '',
    'tournamentIds': [],
    'withOwners': False,
}


def get_random_deck_from_dok(filters={}):
    filter_payload = EMPTY_FILTERS_PAYLOAD | filters
    req_filter_count = post(
        'https://decksofkeyforge.com/api/decks/filter-count',
        json=filter_payload)
    json_filter_count = req_filter_count.json()
    if json_filter_count['count'] == 0:
        return None
    ix_random_deck = randrange(0, json_filter_count['count'])
    page = ix_random_deck // DOK_PAGE_SIZE
    req_filter = post(
        'https://decksofkeyforge.com/api/decks/filter',
        json=(filter_payload | {'page': page}),
        headers={'timezone': '-300'})
    json_req_filter = req_filter.json()
    ix_deck_in_page = ix_random_deck % DOK_PAGE_SIZE
    json_the_deck = json_req_filter['decks'][ix_deck_in_page]
    deck_info = {
        'name': json_the_deck['name'],
        'url': 'https://decksofkeyforge.com/decks/{}'.format(json_the_deck['keyforgeId']),
        'sasRating': json_the_deck['sasRating'],
    }
    return deck_info


def get_random_deck_with_fallback(filters):
    deck_info = get_random_deck_from_dok(filters)
    if deck_info is not None:
        return deck_info, None
    fallback_collection = FallbackCollection.objects.filter(is_active=True).order_by('?').first()
    if fallback_collection is None:
        return None, None
    deck_info = get_random_deck_from_dok(filters | {'owner': fallback_collection.dok_username})
    if deck_info is None:
        return None, None
    return deck_info, fallback_collection.dok_username


def get_filters(owner, min_sas=None, max_sas=None, expansions=None):
    expansion_ids = expansions if expansions else []
    constraints = []
    if min_sas:
        constraints.append({
            'property': 'sasRating',
            'cap': 'MIN',
            'value': min_sas,
        })
    if max_sas:
        constraints.append({
            'property': 'sasRating',
            'cap': 'MAX',
            'value': max_sas,
        })
    filters = {
        'owner': owner,
        'constraints': constraints,
        'expansions': expansion_ids,
    }
    return filters


def get_expansions_from_form(expansion_value):
    if not expansion_value:
        return []
    if expansion_value == 'modern':
        return [*Set.objects.filter(is_legacy=False, is_tournament_legal=True).values_list('id', flat=True)]
    if expansion_value == 'legacy':
        return [*Set.objects.filter(is_legacy=True, is_tournament_legal=True).values_list('id', flat=True)]
    if expansion_value == 'tournament':
        return [*Set.objects.filter(is_tournament_legal=True).values_list('id', flat=True)]
    return [int(expansion_value)]


def random_access_archives(request):
    is_error = False
    deck_info = None
    fallback_collection = None
    if request.method == 'POST':
        form = RandomDecksFromDokForm(request.POST)
        if form.is_valid():
            dok_username = form.cleaned_data['dok_username']
            min_sas = form.cleaned_data['min_sas']
            max_sas = form.cleaned_data['max_sas']
            expansion_value = form.cleaned_data['expansion']
            expansions = get_expansions_from_form(expansion_value)
            filters = get_filters(
                owner=dok_username,
                min_sas=min_sas,
                max_sas=max_sas,
                expansions=expansions,
            )
            try:
                deck_info, fallback_collection = get_random_deck_with_fallback(filters)
            except:
                is_error = True
            if deck_info is None:
                is_error = True

    else:
        form = RandomDecksFromDokForm()

    return render(request, 'redacted/random-access-archives.html', {
        'form': form,
        'deck_info': deck_info,
        'fallback_collection': fallback_collection,
        'is_error': is_error,
    })


def shard_of_knowledge(request):
    return render(request, 'redacted/shard-of-knowledge.html')


def list(request):
    return render(request, 'redacted/list.html')
