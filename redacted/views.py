from random import randrange
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from requests import post
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from .forms import RandomDecksFromDokForm
from allauth.socialaccount.models import SocialAccount
import json
import os

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

public_key = os.environ.get('DISCORD_BOT_PUBLIC_KEY')
verify_key = VerifyKey(bytes.fromhex(public_key))


def get_random_deck_from_dok(filters={}):
    filter_payload = EMPTY_FILTERS_PAYLOAD | filters
    req_filter_count = post(
        'https://decksofkeyforge.com/api/decks/filter-count',
        json=filter_payload)
    json_filter_count = req_filter_count.json()
    ix_random_deck = randrange(0, json_filter_count['count'])
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


@csrf_exempt
def discord_webhook_ingress(request):
    if request.method == 'POST':
        signature = request.META['HTTP_X_SIGNATURE_ED25519']
        timestamp = request.META['HTTP_X_SIGNATURE_TIMESTAMP']
        raw_body = request.body
        body = raw_body.decode('utf-8')

        try:
            verify_key.verify(f'{timestamp}{body}'.encode(), bytes.fromhex(signature))
        except BadSignatureError:
            return HttpResponse('Unauthorized', 401)

        body_json = json.loads(body)

        if body_json['type'] == 1:
            return JsonResponse({ 'type': 1, })
        else:
            try:
                if 'options' in body_json['data']:
                    options = body_json['data'].get('options')
                else:
                    options = []
                owner=from_options('dok', options)
                min_sas=from_options('min', options)
                max_sas=from_options('max', options)
                expansion=from_options('set', options)
                if not owner:
                    sa_id = int(body_json['member']['user']['id'])
                    sa = SocialAccount.objects.get(uid=sa_id)
                    owner = sa.user.profile.dok_handle
                filters = get_filters(owner, min_sas, max_sas, expansion)
                deck_info = get_random_deck_from_dok(filters)
                content = deck_info['url']
                # TODO = put filters in content
                return JsonResponse({
                    'type': 4,
                    'data': {
                        'content': content
                    }
                })
            except:
                return JsonResponse({
                    'type': 4,
                    'data': {
                        'flags': 1<<6,
                        'content': 'Oops! That didn\'t work. Are there decks matching your filter?',
                    }
                })


def from_options(opt_name, options=[]):
    for opt in options:
        if opt['name'] == opt_name:
            return opt['value']
    return None

def get_filters(owner, min_sas=None, max_sas=None, expansion=None):
    expansions = []
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
    filters = {
        'owner': owner,
        'constraints': constraints,
        'expansions': expansions,
    }
    return filters


def random_access_archives(request):
    is_error = False
    deck_info = None
    if request.method == 'POST':
        form = RandomDecksFromDokForm(request.POST)
        if form.is_valid():
            dok_username = form.cleaned_data['dok_username']
            min_sas = form.cleaned_data['min_sas']
            max_sas = form.cleaned_data['max_sas']
            expansion = form.cleaned_data['expansion']
            filters = get_filters(
                owner=dok_username,
                min_sas=min_sas,
                max_sas=max_sas,
                expansion=expansion,
            )
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
