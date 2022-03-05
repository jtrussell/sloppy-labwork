from email import header
from random import randint
from django.shortcuts import render
from requests import post
from .forms import RandomDecksFromDokForm

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
    ix_random_deck = randint(0, json_filter_count['count'])
    page = ix_random_deck // DOK_PAGE_SIZE
    req_filter = post(
        'https://decksofkeyforge.com/api/decks/filter',
        json=(filter_payload | { 'page': page }),
        headers={ 'timezone': '-300' })
    json_req_filter = req_filter.json()
    ix_deck_in_page = ix_random_deck % DOK_PAGE_SIZE
    json_the_deck = json_req_filter['decks'][ix_deck_in_page]
    deck_info = {
        'name': json_the_deck['name'],
        'url': 'https://decksofkeyforge.com/decks/{}'.format(json_the_deck['keyforgeId']),
        'sasRating': json_the_deck['sasRating'],
    }
    return deck_info


def random_access_archives(request):
    is_error = False
    deck_info = None
    if request.method == 'POST':
        form = RandomDecksFromDokForm(request.POST)
        if form.is_valid():
            dok_username = form.cleaned_data['dok_username']
            min_sas = form.cleaned_data['min_sas']
            max_sas = form.cleaned_data['max_sas']
            expansions = []
            expansion = form.cleaned_data['expansion']
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
            if expansion:
                expansions.append(expansion)
            filters = { 'owner': dok_username, 'constraints': constraints,  'expansions': expansions, }
            try:
                deck_info = get_random_deck_from_dok(filters=filters)
            except:
                is_error = True

    else:
        form = RandomDecksFromDokForm()

    return render(request, 'redacted/random-access-archives.html', {
        'form': form,
        'deck_info': deck_info,
        'is_error': is_error,
    })


def list(request):
    return render(request, 'redacted/list.html')
