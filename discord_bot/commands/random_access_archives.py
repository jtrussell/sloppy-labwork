from allauth.socialaccount.models import SocialAccount
from requests import RequestException
from redacted.views import get_random_deck_from_dok, get_filters, get_expansions_from_form
from ..registry import Command, COMMAND_TYPE_CHAT_INPUT, OPTION_TYPE_STRING, OPTION_TYPE_INTEGER, choice
from ..responses import message, ephemeral_message

OPTION_DOK = 'dok'
OPTION_MIN_SAS = 'min'
OPTION_MAX_SAS = 'max'
OPTION_SET = 'set'

SET_GROUPS = {
    1: 'modern',
    2: 'legacy',
    3: 'tournament',
}

SET_CHOICES = [
    choice('Modern', 1),
    choice('Legacy', 2),
    choice('Tournament', 3),
    choice('CotA', 341),
    choice('AoA', 435),
    choice('WC', 452),
    choice('MM', 479),
    choice('DT', 496),
    choice('WoE', 600),
    choice('GR', 700),
    choice('AS', 800),
    choice('ToC', 855),
    choice('MoMu', 874),
    choice('VM23', 609),
    choice('VM24', 737),
    choice('UC22', 601),
    choice('Menagerie', 722),
    choice('PV', 886),
    choice('Discovery', 907),
    choice('CC', 918),
]

NO_DOK_HANDLE_MESSAGE = 'I don\'t know your DoK username. Pass the `dok` option or add your DoK username to your Sloppy Labwork profile.'
NO_DECK_FOUND_MESSAGE = 'Oops! That didn\'t work. Are there decks matching your filter?'

definition = {
    'name': 'random-access-archives',
    'name_localizations': {
        'pl': 'losowy-dostęp-do-archiwum',
    },
    'type': COMMAND_TYPE_CHAT_INPUT,
    'description': 'Grab a random deck from your DoK account',
    'description_localizations': {
        'pl': 'Wybierz losową talię z mojego konta na DoK',
    },
    'options': [
        {
            'name': OPTION_DOK,
            'name_localizations': {
                'pl': 'dok',
            },
            'description': 'Username on Decks of KeyForge',
            'description_localizations': {
                'pl': 'Nazwa użytkownika na DoK',
            },
            'type': OPTION_TYPE_STRING,
            'required': False,
        },
        {
            'name': OPTION_MIN_SAS,
            'name_localizations': {
                'pl': 'min',
            },
            'description': 'Min SAS score',
            'description_localizations': {
                'pl': 'Minimalna wartość SAS',
            },
            'type': OPTION_TYPE_INTEGER,
            'required': False,
        },
        {
            'name': OPTION_MAX_SAS,
            'name_localizations': {
                'pl': 'max',
            },
            'description': 'Max SAS score',
            'description_localizations': {
                'pl': 'Maksymalna wartość SAS',
            },
            'type': OPTION_TYPE_INTEGER,
            'required': False,
        },
        {
            'name': OPTION_SET,
            'name_localizations': {
                'pl': 'dodatek',
            },
            'description': 'Limit to one expansion',
            'description_localizations': {
                'pl': 'Wybierz jedno rozszerzenie',
            },
            'type': OPTION_TYPE_INTEGER,
            'required': False,
            'choices': SET_CHOICES,
        },
    ],
}


def get_dok_handle_for_discord_user(discord_user_id):
    account = SocialAccount.objects.filter(
        provider='discord', uid=discord_user_id).select_related('user__profile').first()
    if account is None:
        return None
    return account.user.profile.dok_handle


def handle(interaction):
    owner = interaction.option(OPTION_DOK) or get_dok_handle_for_discord_user(interaction.user_id)
    if not owner:
        return ephemeral_message(NO_DOK_HANDLE_MESSAGE)
    set_value = interaction.option(OPTION_SET)
    expansions = get_expansions_from_form(SET_GROUPS.get(set_value, set_value))
    filters = get_filters(
        owner,
        interaction.option(OPTION_MIN_SAS),
        interaction.option(OPTION_MAX_SAS),
        expansions,
    )
    try:
        deck_info = get_random_deck_from_dok(filters)
    except (ValueError, KeyError, IndexError, RequestException):
        return ephemeral_message(NO_DECK_FOUND_MESSAGE)
    return message(deck_info['url'])


HELP_TEXT = 'Leave out `dok` to use the DoK username on your Sloppy Labwork profile.'

command = Command(definition, handle, help_text=HELP_TEXT)
