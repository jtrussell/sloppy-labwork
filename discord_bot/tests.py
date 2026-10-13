import json
import os
import time
from unittest import mock
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from nacl.signing import SigningKey
from .interactions import Interaction
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import User
from decks.models import Deck
from lineups.models import Lineup, LineupVersion, LineupVersionDeck
from .responses import (
    MESSAGE_FLAG_EPHEMERAL,
    RESPONSE_TYPE_PONG,
    RESPONSE_TYPE_CHANNEL_MESSAGE,
    RESPONSE_TYPE_UPDATE_MESSAGE,
    RESPONSE_TYPE_AUTOCOMPLETE_RESULT,
)
from .views import dispatch, UNKNOWN_COMMAND_MESSAGE, UNSUPPORTED_INTERACTION_MESSAGE, COMMAND_FAILED_MESSAGE
from .commands import help as help_command, lineup, random_access_archives

DECK_URL = 'https://decksofkeyforge.com/decks/abc'


def command_payload(name, options=None, user_id='42'):
    return {
        'type': 2,
        'data': {'name': name, 'options': options or []},
        'member': {'user': {'id': user_id}},
    }


def autocomplete_payload(name, options=None, user_id='42'):
    return {**command_payload(name, options, user_id), 'type': 4}


def component_payload(custom_id, values, user_id='42'):
    return {
        'type': 3,
        'data': {'custom_id': custom_id, 'values': values},
        'member': {'user': {'id': user_id}},
    }


class InteractionTest(SimpleTestCase):
    def test_reads_user_from_member_in_guilds(self):
        interaction = Interaction({'type': 2, 'member': {'user': {'id': '1'}}})
        self.assertEqual(interaction.user_id, '1')

    def test_reads_user_directly_in_dms(self):
        interaction = Interaction({'type': 2, 'user': {'id': '2'}})
        self.assertEqual(interaction.user_id, '2')

    def test_option_lookup(self):
        interaction = Interaction(command_payload('x', [{'name': 'min', 'value': 70}]))
        self.assertEqual(interaction.option('min'), 70)
        self.assertIsNone(interaction.option('max'))
        self.assertEqual(interaction.option('max', 90), 90)

    def test_subcommand_options_are_unwrapped(self):
        options = [{'name': 'show', 'type': 1, 'options': [{'name': 'lineup', 'type': 3, 'value': 'lnp_A'}]}]
        interaction = Interaction(command_payload('lineup', options))
        self.assertEqual(interaction.subcommand_name, 'show')
        self.assertEqual(interaction.option('lineup'), 'lnp_A')

    def test_focused_option_is_found_for_autocomplete(self):
        options = [{'name': 'show', 'type': 1, 'options': [
            {'name': 'lineup', 'type': 3, 'value': 'lnp_A'},
            {'name': 'version', 'type': 3, 'value': 'v', 'focused': True},
        ]}]
        interaction = Interaction(autocomplete_payload('lineup', options))
        self.assertEqual(interaction.focused_option['name'], 'version')

    def test_component_command_name_comes_from_custom_id(self):
        interaction = Interaction(component_payload('lineup:version', ['lnpv_1']))
        self.assertEqual(interaction.command_name, 'lineup')
        self.assertEqual(interaction.selected_values, ['lnpv_1'])


class DispatchTest(SimpleTestCase):
    def test_ping_is_answered_with_pong(self):
        self.assertEqual(dispatch(Interaction({'type': 1})), {'type': RESPONSE_TYPE_PONG})

    def test_unknown_command_is_an_ephemeral_message(self):
        response = dispatch(Interaction(command_payload('nope')))
        self.assertEqual(response['data']['content'], UNKNOWN_COMMAND_MESSAGE)
        self.assertEqual(response['data']['flags'], MESSAGE_FLAG_EPHEMERAL)

    def test_unsupported_interaction_type_is_an_ephemeral_message(self):
        response = dispatch(Interaction({'type': 5, 'data': {}}))
        self.assertEqual(response['data']['content'], UNSUPPORTED_INTERACTION_MESSAGE)

    def test_autocomplete_for_unknown_command_returns_no_choices(self):
        response = dispatch(Interaction(autocomplete_payload('nope')))
        self.assertEqual(response, {'type': RESPONSE_TYPE_AUTOCOMPLETE_RESULT, 'data': {'choices': []}})

    def test_component_for_command_without_components_is_unknown(self):
        response = dispatch(Interaction(component_payload('random-access-archives:x', [])))
        self.assertEqual(response['data']['content'], UNKNOWN_COMMAND_MESSAGE)

    @mock.patch.object(random_access_archives, 'handle', side_effect=RuntimeError('boom'))
    def test_handler_exceptions_become_an_ephemeral_message(self, _):
        with self.assertLogs('discord_bot.views', level='ERROR'):
            response = dispatch(Interaction(command_payload('random-access-archives')))
        self.assertEqual(response['data']['content'], COMMAND_FAILED_MESSAGE)
        self.assertEqual(response['data']['flags'], MESSAGE_FLAG_EPHEMERAL)


@mock.patch.object(random_access_archives, 'get_random_deck_from_dok', return_value={'url': DECK_URL})
class RandomAccessArchivesTest(SimpleTestCase):
    def test_returns_deck_url_for_given_dok_user(self, get_random_deck):
        options = [
            {'name': 'dok', 'value': 'someone'},
            {'name': 'min', 'value': 70},
            {'name': 'max', 'value': 90},
            {'name': 'set', 'value': 341},
        ]
        response = dispatch(Interaction(command_payload('random-access-archives', options)))
        self.assertEqual(response, {'type': RESPONSE_TYPE_CHANNEL_MESSAGE, 'data': {'content': DECK_URL}})
        filters = get_random_deck.call_args.args[0]
        self.assertEqual(filters['owner'], 'someone')
        self.assertEqual(filters['expansions'], [341])
        self.assertEqual([c['value'] for c in filters['constraints']], [70, 90])

    def test_no_matching_deck_is_an_ephemeral_message(self, get_random_deck):
        get_random_deck.side_effect = ValueError()
        options = [{'name': 'dok', 'value': 'someone'}]
        response = dispatch(Interaction(command_payload('random-access-archives', options)))
        self.assertEqual(response['data']['content'], random_access_archives.NO_DECK_FOUND_MESSAGE)
        self.assertEqual(response['data']['flags'], MESSAGE_FLAG_EPHEMERAL)


class RandomAccessArchivesAccountLookupTest(TestCase):
    def test_unlinked_discord_user_without_dok_option_is_told_so(self):
        response = dispatch(Interaction(command_payload('random-access-archives')))
        self.assertEqual(response['data']['content'], random_access_archives.NO_DOK_HANDLE_MESSAGE)
        self.assertEqual(response['data']['flags'], MESSAGE_FLAG_EPHEMERAL)


def lineup_payload(subcommand, options=None, user_id='42'):
    return command_payload('lineup', [{'name': subcommand, 'type': 1, 'options': options or []}], user_id)


def lineup_autocomplete_payload(options, user_id='42'):
    return autocomplete_payload('lineup', [{'name': 'show', 'type': 1, 'options': options}], user_id)


class LineupCommandTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner')
        SocialAccount.objects.create(user=self.owner, provider='discord', uid='42')
        self.stranger = User.objects.create_user('stranger')
        SocialAccount.objects.create(user=self.stranger, provider='discord', uid='99')

        self.private_lineup = Lineup.objects.create(owner=self.owner, name='Vault Tour')
        self.older_version = LineupVersion.objects.create(
            lineup=self.private_lineup, name='v1', sort_order=1)
        self.latest_version = LineupVersion.objects.create(
            lineup=self.private_lineup, name='v2', sort_order=2)
        deck = Deck.objects.create(id='00000000-0000-0000-0000-000000000001', name='The Deck')
        LineupVersionDeck.objects.create(version=self.latest_version, deck=deck)

        self.public_lineup = Lineup.objects.create(
            owner=self.owner, name='Open Lineup', visibility=Lineup.Visibility.PUBLIC)
        self.public_version = LineupVersion.objects.create(
            lineup=self.public_lineup, name='Only', sort_order=1)
        self.hidden_public_version = LineupVersion.objects.create(
            lineup=self.public_lineup, name='Secret', sort_order=2,
            visibility_override=LineupVersion.Visibility.UNLISTED)

    def show(self, options, user_id='42'):
        return dispatch(Interaction(lineup_payload('show', options, user_id)))

    def test_list_for_unlinked_user_asks_them_to_link(self):
        response = dispatch(Interaction(lineup_payload('list', user_id='7')))
        self.assertIn('Link your Discord account', response['data']['content'])
        self.assertEqual(response['data']['flags'], MESSAGE_FLAG_EPHEMERAL)

    def test_list_shows_only_own_lineups_privately(self):
        Lineup.objects.create(owner=self.stranger, name='Not Mine')
        response = dispatch(Interaction(lineup_payload('list')))
        description = response['data']['embeds'][0]['description']
        self.assertIn('Vault Tour', description)
        self.assertIn('Open Lineup', description)
        self.assertNotIn('Not Mine', description)
        self.assertEqual(response['data']['flags'], MESSAGE_FLAG_EPHEMERAL)

    def test_list_with_no_lineups_points_to_create(self):
        response = dispatch(Interaction(lineup_payload('list', user_id='99')))
        self.assertIn('/lineups/new/', response['data']['content'])

    def test_show_defaults_to_latest_version_with_version_select(self):
        response = self.show([{'name': 'lineup', 'value': self.private_lineup.code}])
        embed = response['data']['embeds'][0]
        self.assertEqual(embed['title'], 'Vault Tour — v2')
        self.assertIn('The Deck', embed['description'])
        self.assertEqual(response['data']['flags'], MESSAGE_FLAG_EPHEMERAL)
        select = response['data']['components'][0]['components'][0]
        self.assertEqual(select['custom_id'], lineup.VERSION_SELECT_CUSTOM_ID)
        self.assertEqual([option['value'] for option in select['options']],
                         [self.latest_version.code, self.older_version.code])

    def test_show_accepts_own_lineup_and_version_by_name(self):
        response = self.show([
            {'name': 'lineup', 'value': 'vault tour'},
            {'name': 'version', 'value': 'V1'},
        ])
        self.assertEqual(response['data']['embeds'][0]['title'], 'Vault Tour — v1')

    def test_show_hides_private_lineup_from_others(self):
        response = self.show([{'name': 'lineup', 'value': self.private_lineup.code}], user_id='99')
        self.assertEqual(response['data']['content'], lineup.LINEUP_NOT_FOUND_MESSAGE)

    def test_show_finds_public_lineup_by_code_for_unlinked_user(self):
        response = self.show([{'name': 'lineup', 'value': self.public_lineup.code}], user_id='7')
        embed = response['data']['embeds'][0]
        self.assertEqual(embed['title'], 'Open Lineup — Only')
        self.assertEqual(response['data']['components'], [])

    def test_post_in_channel_refuses_private_lineup(self):
        response = self.show([
            {'name': 'lineup', 'value': self.private_lineup.code},
            {'name': 'post-in-channel', 'value': True},
        ])
        self.assertEqual(response['data']['content'], lineup.PRIVATE_LINEUP_MESSAGE)

    def test_post_in_channel_posts_public_lineup_without_components(self):
        response = self.show([
            {'name': 'lineup', 'value': self.public_lineup.code},
            {'name': 'version', 'value': self.public_version.code},
            {'name': 'post-in-channel', 'value': True},
        ])
        self.assertNotIn('flags', response['data'])
        self.assertEqual(response['data']['components'], [])

    def test_lineup_autocomplete_suggests_only_own_lineups(self):
        Lineup.objects.create(owner=self.stranger, name='Vault Rival')
        response = dispatch(Interaction(lineup_autocomplete_payload([
            {'name': 'lineup', 'type': 3, 'value': 'vault', 'focused': True},
        ])))
        self.assertEqual(response['type'], RESPONSE_TYPE_AUTOCOMPLETE_RESULT)
        self.assertEqual(response['data']['choices'],
                         [{'name': 'Vault Tour', 'value': self.private_lineup.code}])

    def test_version_autocomplete_uses_selected_lineup_and_visibility(self):
        response = dispatch(Interaction(lineup_autocomplete_payload([
            {'name': 'lineup', 'type': 3, 'value': self.public_lineup.code},
            {'name': 'version', 'type': 3, 'value': '', 'focused': True},
        ], user_id='99')))
        self.assertEqual([c['value'] for c in response['data']['choices']], [self.public_version.code])

    def test_version_select_updates_message(self):
        response = dispatch(Interaction(component_payload(
            lineup.VERSION_SELECT_CUSTOM_ID, [self.older_version.code])))
        self.assertEqual(response['type'], RESPONSE_TYPE_UPDATE_MESSAGE)
        self.assertEqual(response['data']['embeds'][0]['title'], 'Vault Tour — v1')

    def test_version_select_rejects_versions_the_user_cannot_view(self):
        response = dispatch(Interaction(component_payload(
            lineup.VERSION_SELECT_CUSTOM_ID, [self.older_version.code], user_id='99')))
        self.assertEqual(response['data']['content'], lineup.VERSION_NOT_FOUND_MESSAGE)


class HelpCommandTest(SimpleTestCase):
    def help(self, options=None):
        return dispatch(Interaction(command_payload('help', options)))

    def test_overview_lists_every_command_privately(self):
        response = self.help()
        description = response['data']['embeds'][0]['description']
        for name in ['help', 'lineup', 'random-access-archives']:
            self.assertIn(f'`/{name}`', description)
        self.assertEqual(response['data']['flags'], MESSAGE_FLAG_EPHEMERAL)

    def test_usage_for_command_with_subcommands(self):
        response = self.help([{'name': 'command', 'value': 'lineup'}])
        embed = response['data']['embeds'][0]
        self.assertEqual(embed['title'], '/lineup')
        self.assertIn('`/lineup list`', embed['description'])
        self.assertIn(
            '`/lineup show lineup:<text> [version:<text>] [post-in-channel:<true/false>]`',
            embed['description'])
        self.assertIn(lineup.HELP_TEXT, embed['description'])

    def test_usage_for_command_without_subcommands_lists_choices(self):
        response = self.help([{'name': 'command', 'value': '/Random-Access-Archives'}])
        description = response['data']['embeds'][0]['description']
        self.assertIn('`/random-access-archives [dok:<text>] [min:<number>]', description)
        self.assertIn('One of: Modern, Legacy', description)
        self.assertEqual(description.count(random_access_archives.definition['description']), 1)

    def test_unknown_command(self):
        response = self.help([{'name': 'command', 'value': 'nope'}])
        self.assertEqual(response['data']['content'], help_command.unknown_command_message('nope'))

    def test_autocomplete_filters_command_names(self):
        response = dispatch(Interaction(autocomplete_payload('help', [
            {'name': 'command', 'type': 3, 'value': 'line', 'focused': True},
        ])))
        self.assertEqual(response['data']['choices'], [{'name': 'lineup', 'value': 'lineup'}])


class InteractionsEndpointTest(SimpleTestCase):
    def setUp(self):
        self.signing_key = SigningKey.generate()
        public_key = self.signing_key.verify_key.encode().hex()
        patcher = mock.patch.dict(os.environ, {'DISCORD_BOT_PUBLIC_KEY': public_key})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.url = reverse('discord-interactions')

    def post(self, payload, signature=None):
        body = json.dumps(payload).encode()
        timestamp = str(int(time.time()))
        if signature is None:
            signature = self.signing_key.sign(timestamp.encode() + body).signature.hex()
        return self.client.post(
            self.url,
            data=body,
            content_type='application/json',
            headers={'X-Signature-Ed25519': signature, 'X-Signature-Timestamp': timestamp},
        )

    def test_signed_ping_is_answered(self):
        response = self.post({'type': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'type': RESPONSE_TYPE_PONG})

    def test_bad_signature_is_rejected(self):
        response = self.post({'type': 1}, signature='00' * 64)
        self.assertEqual(response.status_code, 401)

    def test_missing_signature_is_rejected(self):
        response = self.client.post(self.url, data=b'{"type": 1}', content_type='application/json')
        self.assertEqual(response.status_code, 401)

    def test_legacy_webhook_path_still_works(self):
        response = self.client.post(
            '/redacted/discord-webhook/',
            data=b'{"type": 1}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)
