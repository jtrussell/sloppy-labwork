from decks.models import Deck


DECK_SUGGESTION_LIMIT = 5
MINIMUM_DECK_NAME_QUERY_LENGTH = 2
DECK_NAME_OPTIONS_TEMPLATE = 'lineups/partials/deck-name-options.html'


def looks_like_deck_link(deck_input):
    return '/' in deck_input or 'http' in deck_input.lower()


def get_decks_in_lineups_owned_by(user):
    return Deck.objects.filter(lineup_versions__version__lineup__owner=user).distinct()


def find_lineup_decks_matching_name(user, name_query):
    if len(name_query) < MINIMUM_DECK_NAME_QUERY_LENGTH or looks_like_deck_link(name_query):
        return Deck.objects.none()
    return get_decks_in_lineups_owned_by(user).filter(name__icontains=name_query).order_by('name')


def find_lineup_deck_named(user, deck_name):
    return get_decks_in_lineups_owned_by(user).filter(name__iexact=deck_name).order_by('name').first()
