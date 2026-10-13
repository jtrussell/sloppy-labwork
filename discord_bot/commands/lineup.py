from django.db.models import Count
from decks.models import Deck
from lineups.models import Lineup, LineupVersion
from ..accounts import get_site_user_for_discord_id
from ..interactions import CUSTOM_ID_SEPARATOR
from ..links import absolute_url
from ..registry import (
    Command,
    COMMAND_TYPE_CHAT_INPUT,
    OPTION_TYPE_SUB_COMMAND,
    OPTION_TYPE_STRING,
    OPTION_TYPE_BOOLEAN,
    choice,
)
from ..responses import (
    ephemeral_message,
    embed_message,
    update_message,
    autocomplete_choices,
    action_row,
    string_select,
    select_option,
)

COMMAND_NAME = 'lineup'
SUBCOMMAND_LIST = 'list'
SUBCOMMAND_SHOW = 'show'
OPTION_LINEUP = 'lineup'
OPTION_VERSION = 'version'
OPTION_POST_IN_CHANNEL = 'post-in-channel'
VERSION_SELECT_CUSTOM_ID = CUSTOM_ID_SEPARATOR.join([COMMAND_NAME, 'version'])

LIST_LIMIT = 10
MAX_CHOICES = 25
MAX_CHOICE_NAME_LENGTH = 100
MAX_EMBED_TITLE_LENGTH = 256
MAX_EMBED_DESCRIPTION_LENGTH = 4096

SHAREABLE_VISIBILITIES = (Lineup.Visibility.PUBLIC, Lineup.Visibility.UNLISTED)

LINEUP_NOT_FOUND_MESSAGE = 'I couldn\'t find that lineup, or you don\'t have access to it.'
VERSION_NOT_FOUND_MESSAGE = 'I couldn\'t find a version of that lineup to show you.'
PRIVATE_LINEUP_MESSAGE = 'That lineup is private, so I won\'t post it in the channel. Make it public or unlisted on Sloppy Labwork first.'
NO_DECKS_MESSAGE = 'No decks in this version yet.'
UNNAMED_DECK = 'Unnamed deck'

definition = {
    'name': COMMAND_NAME,
    'type': COMMAND_TYPE_CHAT_INPUT,
    'description': 'Browse your Sloppy Labwork lineups',
    'options': [
        {
            'name': SUBCOMMAND_LIST,
            'description': 'List your most recently updated lineups',
            'type': OPTION_TYPE_SUB_COMMAND,
        },
        {
            'name': SUBCOMMAND_SHOW,
            'description': 'Show the decks in a lineup',
            'type': OPTION_TYPE_SUB_COMMAND,
            'options': [
                {
                    'name': OPTION_LINEUP,
                    'description': 'Lineup name or code',
                    'type': OPTION_TYPE_STRING,
                    'required': True,
                    'autocomplete': True,
                },
                {
                    'name': OPTION_VERSION,
                    'description': 'Lineup version (defaults to the latest)',
                    'type': OPTION_TYPE_STRING,
                    'required': False,
                    'autocomplete': True,
                },
                {
                    'name': OPTION_POST_IN_CHANNEL,
                    'description': 'Post the lineup in this channel instead of only showing it to you',
                    'type': OPTION_TYPE_BOOLEAN,
                    'required': False,
                },
            ],
        },
    ],
}


def truncate(text, max_length):
    if len(text) <= max_length:
        return text
    return text[:max_length - 1] + '…'


def account_not_linked_message():
    connections_url = absolute_url('socialaccount_connections')
    return f'I don\'t know which Sloppy Labwork account is yours. Link your Discord account at {connections_url} and try again.'


def no_lineups_message():
    create_url = absolute_url('lineups-create')
    return f'You don\'t have any lineups yet. Create one at {create_url}'


def find_viewable_lineup(lineup_value, user):
    lineup = Lineup.objects.select_related('format').filter(code=lineup_value).first()
    if lineup is None and user.is_authenticated:
        lineup = user.lineups.select_related('format').filter(name__iexact=lineup_value).first()
    if lineup is None or not lineup.can_view(user):
        return None
    return lineup


def get_visible_versions_newest_first(lineup, user):
    return lineup.get_visible_versions(user).order_by('-sort_order')


def find_viewable_version(lineup, version_value, user):
    if not version_value:
        return get_visible_versions_newest_first(lineup, user).first()
    version = lineup.versions.filter(code=version_value).first()
    if version is None:
        version = get_visible_versions_newest_first(lineup, user).filter(name__iexact=version_value).first()
    if version is None or not version.can_view(user):
        return None
    return version


def describe_lineup_in_list(lineup):
    lineup_url = absolute_url('lineups-detail', lineup.code)
    details = [lineup.format.name] if lineup.format else []
    details.append(f'{lineup.version_count} version' + ('' if lineup.version_count == 1 else 's'))
    details.append(f'`{lineup.code}`')
    return f'**[{lineup.name}]({lineup_url})** · ' + ' · '.join(details)


def describe_deck_in_version(position, deck):
    deck_url = Deck.get_master_vault_ui_url_from_id(deck.id)
    houses = [house.name for house in (deck.house_1, deck.house_2, deck.house_3) if house]
    details = ([deck.set.name] if deck.set else []) + ([' / '.join(houses)] if houses else [])
    line = f'{position}. [{deck.name or UNNAMED_DECK}]({deck_url})'
    if details:
        line += ' · ' + ' · '.join(details)
    return line


def build_version_embed(version):
    lineup = version.lineup
    version_decks = version.version_decks.select_related(
        'deck__set', 'deck__house_1', 'deck__house_2', 'deck__house_3')
    deck_lines = [
        describe_deck_in_version(position, version_deck.deck)
        for position, version_deck in enumerate(version_decks, start=1)
    ]
    footer_parts = ([lineup.format.name] if lineup.format else []) + [version.code]
    return {
        'title': truncate(f'{lineup.name} — {version.name}', MAX_EMBED_TITLE_LENGTH),
        'url': absolute_url('lineups-version-detail', version.code),
        'description': truncate('\n'.join(deck_lines) or NO_DECKS_MESSAGE, MAX_EMBED_DESCRIPTION_LENGTH),
        'footer': {'text': ' · '.join(footer_parts)},
    }


def build_version_select_components(lineup, selected_version, user):
    versions = list(get_visible_versions_newest_first(lineup, user)[:MAX_CHOICES])
    if len(versions) < 2:
        return []
    options = [
        select_option(
            truncate(version.name, MAX_CHOICE_NAME_LENGTH),
            version.code,
            default=version.pk == selected_version.pk,
        )
        for version in versions
    ]
    return [action_row(string_select(VERSION_SELECT_CUSTOM_ID, options, placeholder='Switch version'))]


def list_lineups(interaction, user):
    if not user.is_authenticated:
        return ephemeral_message(account_not_linked_message())
    lineups = list(
        user.lineups.select_related('format')
        .annotate(version_count=Count('versions'))[:LIST_LIMIT]
    )
    if not lineups:
        return ephemeral_message(no_lineups_message())
    embed = {
        'title': 'Your lineups',
        'url': absolute_url('lineups-list'),
        'description': truncate(
            '\n'.join(describe_lineup_in_list(lineup) for lineup in lineups),
            MAX_EMBED_DESCRIPTION_LENGTH),
    }
    return embed_message([embed], ephemeral=True)


def show_lineup(interaction, user):
    lineup = find_viewable_lineup(interaction.option(OPTION_LINEUP), user)
    if lineup is None:
        return ephemeral_message(LINEUP_NOT_FOUND_MESSAGE)
    version = find_viewable_version(lineup, interaction.option(OPTION_VERSION), user)
    if version is None:
        return ephemeral_message(VERSION_NOT_FOUND_MESSAGE)
    embed = build_version_embed(version)
    if interaction.option(OPTION_POST_IN_CHANNEL, False):
        if version.get_effective_visibility() not in SHAREABLE_VISIBILITIES:
            return ephemeral_message(PRIVATE_LINEUP_MESSAGE)
        return embed_message([embed])
    components = build_version_select_components(lineup, version, user)
    return embed_message([embed], components=components, ephemeral=True)


SUBCOMMAND_HANDLERS = {
    SUBCOMMAND_LIST: list_lineups,
    SUBCOMMAND_SHOW: show_lineup,
}


def handle(interaction):
    user = get_site_user_for_discord_id(interaction.user_id)
    return SUBCOMMAND_HANDLERS[interaction.subcommand_name](interaction, user)


def lineup_choices(user, query):
    if not user.is_authenticated:
        return []
    lineups = user.lineups.filter(name__icontains=query)[:MAX_CHOICES]
    return [choice(truncate(lineup.name, MAX_CHOICE_NAME_LENGTH), lineup.code) for lineup in lineups]


def version_choices(user, lineup_value, query):
    lineup = find_viewable_lineup(lineup_value, user) if lineup_value else None
    if lineup is None:
        return []
    versions = get_visible_versions_newest_first(lineup, user).filter(name__icontains=query)[:MAX_CHOICES]
    return [choice(truncate(version.name, MAX_CHOICE_NAME_LENGTH), version.code) for version in versions]


def autocomplete(interaction):
    user = get_site_user_for_discord_id(interaction.user_id)
    focused_option = interaction.focused_option or {}
    query = focused_option.get('value', '')
    if focused_option.get('name') == OPTION_LINEUP:
        return autocomplete_choices(lineup_choices(user, query))
    if focused_option.get('name') == OPTION_VERSION:
        return autocomplete_choices(version_choices(user, interaction.option(OPTION_LINEUP), query))
    return autocomplete_choices([])


def handle_version_select(interaction):
    user = get_site_user_for_discord_id(interaction.user_id)
    selected_code = next(iter(interaction.selected_values), None)
    version = LineupVersion.objects.select_related(
        'lineup__format').filter(code=selected_code).first()
    if version is None or not version.can_view(user):
        return ephemeral_message(VERSION_NOT_FOUND_MESSAGE)
    components = build_version_select_components(version.lineup, version, user)
    return update_message([build_version_embed(version)], components=components)


command = Command(definition, handle, autocomplete=autocomplete, component=handle_version_select)
