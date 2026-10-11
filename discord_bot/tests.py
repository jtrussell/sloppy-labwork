import json
import os
import time
from unittest import mock
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from nacl.signing import SigningKey
from .interactions import Interaction
from .responses import MESSAGE_FLAG_EPHEMERAL, RESPONSE_TYPE_PONG, RESPONSE_TYPE_CHANNEL_MESSAGE
from .views import dispatch, UNKNOWN_COMMAND_MESSAGE, UNSUPPORTED_INTERACTION_MESSAGE, COMMAND_FAILED_MESSAGE
from .commands import random_access_archives

DECK_URL = 'https://decksofkeyforge.com/decks/abc'


def command_payload(name, options=None, user_id='42'):
    return {
        'type': 2,
        'data': {'name': name, 'options': options or []},
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


class DispatchTest(SimpleTestCase):
    def test_ping_is_answered_with_pong(self):
        self.assertEqual(dispatch(Interaction({'type': 1})), {'type': RESPONSE_TYPE_PONG})

    def test_unknown_command_is_an_ephemeral_message(self):
        response = dispatch(Interaction(command_payload('nope')))
        self.assertEqual(response['data']['content'], UNKNOWN_COMMAND_MESSAGE)
        self.assertEqual(response['data']['flags'], MESSAGE_FLAG_EPHEMERAL)

    def test_unsupported_interaction_type_is_an_ephemeral_message(self):
        response = dispatch(Interaction({'type': 3, 'data': {}}))
        self.assertEqual(response['data']['content'], UNSUPPORTED_INTERACTION_MESSAGE)

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
