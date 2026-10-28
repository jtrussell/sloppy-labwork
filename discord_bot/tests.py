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
from decks.models import Deck, Set
from ghostform.models import Answer, Form as GhostformForm, Question as GhostformQuestion
from lineups.models import Lineup, LineupVersion, LineupVersionDeck
from tourney.models import Match, MatchResult, Player, Pod, Round, Stage, StagePlayer, Tournament
from .responses import (
    MESSAGE_FLAG_EPHEMERAL,
    RESPONSE_TYPE_PONG,
    RESPONSE_TYPE_CHANNEL_MESSAGE,
    RESPONSE_TYPE_UPDATE_MESSAGE,
    RESPONSE_TYPE_AUTOCOMPLETE_RESULT,
    RESPONSE_TYPE_MODAL,
)
from .views import dispatch, UNKNOWN_COMMAND_MESSAGE, UNSUPPORTED_INTERACTION_MESSAGE, COMMAND_FAILED_MESSAGE
from .commands import help as help_command, lineup, random_access_archives, tourney

DECK_URL = 'https://decksofkeyforge.com/decks/abc'


def command_payload(name, options=None, user_id='42'):
    return {
        'type': 2,
        'data': {'name': name, 'options': options or []},
        'member': {'user': {'id': user_id}},
    }


def autocomplete_payload(name, options=None, user_id='42'):
    return {**command_payload(name, options, user_id), 'type': 4}


def modal_submit_payload(custom_id, components, user_id='42'):
    return {
        'type': 5,
        'data': {'custom_id': custom_id, 'components': components},
        'member': {'user': {'id': user_id}},
    }


def labelled(custom_id, **submitted):
    return {'type': 18, 'component': {'custom_id': custom_id, **submitted}}


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

    def test_submitted_values_are_read_from_labels_and_action_rows(self):
        interaction = Interaction(modal_submit_payload('tourney:report-match:1', [
            labelled('winner', value='7'),
            labelled('opponent', values=['3']),
            labelled('agreed', value=True),
            {'type': 1, 'components': [{'type': 4, 'custom_id': 'legacy', 'value': 'old'}]},
            {'type': 10, 'id': 9},
        ]))
        self.assertEqual(interaction.command_name, 'tourney')
        self.assertEqual(interaction.submitted_values, {
            'winner': '7', 'opponent': ['3'], 'agreed': True, 'legacy': 'old'})

    def test_component_command_name_comes_from_custom_id(self):
        interaction = Interaction(component_payload('lineup:version', ['lnpv_1']))
        self.assertEqual(interaction.command_name, 'lineup')
        self.assertEqual(interaction.selected_values, ['lnpv_1'])


class DispatchTest(SimpleTestCase):
    def test_ping_is_answered_with_pong(self):
        self.assertEqual(dispatch(Interaction({'type': 1})), {'type': RESPONSE_TYPE_PONG})

    def test_unknown_command_is_an_ephemeral_message(self):
        with self.assertLogs('discord_bot.views', level='WARNING'):
            response = dispatch(Interaction(command_payload('nope')))
        self.assertEqual(response['data']['content'], UNKNOWN_COMMAND_MESSAGE)
        self.assertEqual(response['data']['flags'], MESSAGE_FLAG_EPHEMERAL)

    def test_unsupported_interaction_type_is_an_ephemeral_message(self):
        with self.assertLogs('discord_bot.views', level='WARNING'):
            response = dispatch(Interaction({'type': 99, 'data': {}}))
        self.assertEqual(response['data']['content'], UNSUPPORTED_INTERACTION_MESSAGE)

    def test_autocomplete_for_unknown_command_returns_no_choices(self):
        with self.assertLogs('discord_bot.views', level='WARNING'):
            response = dispatch(Interaction(autocomplete_payload('nope')))
        self.assertEqual(response, {'type': RESPONSE_TYPE_AUTOCOMPLETE_RESULT, 'data': {'choices': []}})

    def test_component_for_command_without_components_is_unknown(self):
        with self.assertLogs('discord_bot.views', level='WARNING'):
            response = dispatch(Interaction(component_payload('random-access-archives:x', [])))
        self.assertEqual(response['data']['content'], UNKNOWN_COMMAND_MESSAGE)

    @mock.patch.object(random_access_archives, 'handle', side_effect=RuntimeError('boom'))
    def test_handler_exceptions_become_an_ephemeral_message(self, _):
        with self.assertLogs('discord_bot.views', level='ERROR'):
            response = dispatch(Interaction(command_payload('random-access-archives')))
        self.assertEqual(response['data']['content'], COMMAND_FAILED_MESSAGE)
        self.assertEqual(response['data']['flags'], MESSAGE_FLAG_EPHEMERAL)


@mock.patch.object(random_access_archives, 'get_random_deck_with_fallback', return_value=({'url': DECK_URL}, None))
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

    def test_no_deck_in_any_collection_is_an_ephemeral_message(self, get_random_deck):
        get_random_deck.return_value = (None, None)
        options = [{'name': 'dok', 'value': 'someone'}]
        response = dispatch(Interaction(command_payload('random-access-archives', options)))
        self.assertEqual(response['data']['content'], random_access_archives.NO_DECK_FOUND_MESSAGE)
        self.assertEqual(response['data']['flags'], MESSAGE_FLAG_EPHEMERAL)

    def test_deck_from_fallback_collection_names_the_collection(self, get_random_deck):
        get_random_deck.return_value = ({'url': DECK_URL}, 'vault-keeper')
        options = [{'name': 'dok', 'value': 'someone'}]
        response = dispatch(Interaction(command_payload('random-access-archives', options)))
        self.assertEqual(response, {
            'type': RESPONSE_TYPE_CHANNEL_MESSAGE,
            'data': {'content': random_access_archives.fallback_deck_message('vault-keeper', DECK_URL)},
        })
        self.assertIn('vault-keeper', response['data']['content'])


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
        deck_set = Set.objects.create(
            id=341, name='Call of the Archons', short_name='CotA', src='https://example.com/cota.png')
        deck = Deck.objects.create(
            id='00000000-0000-0000-0000-000000000001', name='The Deck', set=deck_set)
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
        self.assertIn(
            '1. **The Deck** · CotA · '
            '[DoK](https://decksofkeyforge.com/decks/00000000-0000-0000-0000-000000000001) · '
            '[MV](https://www.keyforgegame.com/deck-details/00000000-0000-0000-0000-000000000001)',
            embed['description'])
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


class TourneyReportCommandTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('tourney-owner')
        self.tournament = Tournament.objects.create(name='Spring Open', owner=self.owner)
        self.stage = Stage.objects.create(
            tournament=self.tournament, name='Swiss', order=1, pairing_strategy='swiss',
            report_full_scores=Stage.SCORE_REPORTING_OPTIONAL)
        self.stage_players = []
        for seed, nickname in enumerate(['Anvil', 'Beacon', 'Comet'], start=1):
            user = User.objects.create_user(nickname.lower())
            SocialAccount.objects.create(user=user, provider='discord', uid=str(seed))
            player = Player.objects.create(user=user, tournament=self.tournament, nickname=nickname)
            self.stage_players.append(StagePlayer.objects.create(player=player, stage=self.stage, seed=seed))
        self.anvil, self.beacon, self.comet = self.stage_players
        self.round = Round.objects.create(stage=self.stage, order=1)
        self.match = Match.objects.create(round=self.round, player_one=self.anvil, player_two=self.beacon)

    def report(self, options=None, user_id='1'):
        return dispatch(Interaction(command_payload(
            'tourney', [{'name': 'report', 'type': 1, 'options': options or []}], user_id)))

    def submit(self, custom_id, components, user_id='1'):
        return dispatch(Interaction(modal_submit_payload(custom_id, components, user_id)))

    def paired_custom_id(self):
        return f'tourney:report-match:{self.match.id}'

    def modal_custom_ids(self, response):
        return [component['component']['custom_id'] for component in response['data']['components']]

    def add_result_form(self, *questions):
        result_form = GhostformForm.objects.create(
            owner=self.owner, title='Deck Check', status=GhostformForm.Status.PUBLISHED)
        for order, (question_label, answer_type, extra) in enumerate(questions, start=1):
            GhostformQuestion.objects.create(
                form=result_form, label=question_label, order=order, answer_type=answer_type, **extra)
        self.tournament.result_form = result_form
        self.tournament.save()
        return result_form

    def test_unlinked_user_is_asked_to_link(self):
        response = self.report(user_id='404')
        self.assertIn('Link your Discord account', response['data']['content'])

    def test_user_without_open_tournaments_is_told_so(self):
        self.tournament.is_closed = True
        self.tournament.save()
        response = self.report()
        self.assertEqual(response['data']['content'], tourney.NO_OPEN_TOURNAMENTS_MESSAGE)

    def test_user_in_two_tournaments_must_choose_and_can_autocomplete(self):
        other = Tournament.objects.create(name='Spring Side Event', owner=self.owner)
        Player.objects.create(user=self.anvil.player.user, tournament=other)

        response = self.report()
        self.assertEqual(response['data']['content'], tourney.CHOOSE_TOURNAMENT_MESSAGE)

        suggestions = dispatch(Interaction(autocomplete_payload('tourney', [{'name': 'report', 'type': 1, 'options': [
            {'name': 'tournament', 'type': 3, 'value': 'spring', 'focused': True}]}], user_id='1')))
        self.assertEqual({c['value'] for c in suggestions['data']['choices']}, {self.tournament.code, other.code})

    def test_paired_report_opens_modal_with_winner_and_scores(self):
        response = self.report()
        self.assertEqual(response['type'], RESPONSE_TYPE_MODAL)
        self.assertEqual(response['data']['custom_id'], self.paired_custom_id())
        self.assertEqual(self.modal_custom_ids(response), ['winner', 'player_one_score', 'player_two_score'])
        winner_values = [option['value'] for option in response['data']['components'][0]['component']['options']]
        self.assertEqual(winner_values, [str(self.anvil.id), str(self.beacon.id)])

    def test_paired_report_with_result_already_recorded_is_refused(self):
        MatchResult.objects.create(match=self.match, winner=self.beacon)
        response = self.report()
        self.assertEqual(response['data']['content'], tourney.MATCH_ALREADY_REPORTED_MESSAGE)

    def test_paired_submission_saves_result_and_posts_publicly(self):
        response = self.submit(self.paired_custom_id(), [
            labelled('winner', value=str(self.anvil.id)),
            labelled('player_one_score', value='3'),
            labelled('player_two_score', value='1'),
        ])
        self.assertEqual(MatchResult.objects.get(match=self.match).winner, self.anvil)
        self.assertNotIn('flags', response['data'])
        self.assertEqual(response['data']['content'], '**Spring Open** · Swiss · Round 1 — Anvil beat Beacon 3–1')

    def test_tie_is_described(self):
        self.stage.are_ties_allowed = True
        self.stage.save()
        response = self.submit(self.paired_custom_id(), [labelled('winner', value='tie')])
        self.assertTrue(MatchResult.objects.get(match=self.match).is_tie())
        self.assertTrue(response['data']['content'].endswith('Anvil and Beacon tied'))

    def test_invalid_submission_offers_retry(self):
        response = self.submit(self.paired_custom_id(), [
            labelled('winner', value=str(self.anvil.id)),
            labelled('player_one_score', value='three'),
            labelled('player_two_score', value='1'),
        ])
        self.assertFalse(MatchResult.objects.exists())
        self.assertTrue(response['data']['content'].startswith(tourney.REPORT_FAILED_INTRO))
        retry_button = response['data']['components'][0]['components'][0]
        self.assertEqual(retry_button['custom_id'], f'tourney:retry:{self.tournament.code}')

        retry = dispatch(Interaction(component_payload(retry_button['custom_id'], [], user_id='1')))
        self.assertEqual(retry['type'], RESPONSE_TYPE_MODAL)

    def test_outsider_submission_is_not_allowed(self):
        response = self.submit(
            self.paired_custom_id(), [labelled('winner', value=str(self.anvil.id))], user_id='3')
        self.assertEqual(response['data']['content'], tourney.NOT_ALLOWED_MESSAGE)

    def test_result_form_questions_are_asked_and_recorded(self):
        result_form = self.add_result_form(
            ('Your deck', GhostformQuestion.AnswerType.DECK_LINK, {'is_required': True}),
            ('First player?', GhostformQuestion.AnswerType.MULTIPLE_CHOICE, {'choices': ['Me', 'Them']}),
        )
        deck_question, choice_question = result_form.get_active_questions()
        self.stage.report_full_scores = Stage.SCORE_REPORTING_DISABLED
        self.stage.save()
        deck_field = f'ghostform-{deck_question.get_field_name()}'
        choice_field = f'ghostform-{choice_question.get_field_name()}'

        response = self.report()
        self.assertEqual(self.modal_custom_ids(response), ['winner', deck_field, choice_field])

        deck_link = 'https://decksofkeyforge.com/decks/00000000-0000-0000-0000-000000000001'
        self.submit(self.paired_custom_id(), [
            labelled('winner', value=str(self.beacon.id)),
            labelled(deck_field, value=deck_link),
            labelled(choice_field, values=['1']),
        ])
        self.assertEqual(MatchResult.objects.get(match=self.match).winner, self.beacon)
        self.assertEqual(
            sorted(Answer.objects.values_list('value', flat=True)), sorted([deck_link, 'Them']))

    def test_multiple_answer_question_allows_several_selections(self):
        result_form = self.add_result_form(
            ('Houses faced', GhostformQuestion.AnswerType.MULTIPLE_CHOICE,
             {'choices': ['Brobnar', 'Dis', 'Mars'], 'allows_multiple_answers': True}),
        )
        choice_question = result_form.get_active_questions().get()
        choice_field = f'ghostform-{choice_question.get_field_name()}'

        response = self.report()
        choice_select = response['data']['components'][-1]['component']
        self.assertEqual(choice_select['max_values'], 3)

        self.submit(self.paired_custom_id(), [
            labelled('winner', value=str(self.anvil.id)),
            labelled('player_one_score', value='3'),
            labelled('player_two_score', value='1'),
            labelled(choice_field, values=['0', '2']),
        ])
        self.assertEqual(Answer.objects.get().value, 'Brobnar\nMars')

    def test_selection_limits_are_applied_to_the_select_menu(self):
        self.add_result_form(
            ('Houses faced', GhostformQuestion.AnswerType.MULTIPLE_CHOICE, {
                'choices': ['Brobnar', 'Dis', 'Logos', 'Mars'], 'allows_multiple_answers': True,
                'is_required': True, 'minimum_selections': 3, 'maximum_selections': 3}),
        )

        choice_select = self.report()['data']['components'][-1]['component']

        self.assertEqual((choice_select['min_values'], choice_select['max_values']), (3, 3))

    def test_missing_required_answer_is_reported(self):
        self.add_result_form(('Your deck', GhostformQuestion.AnswerType.DECK_LINK, {'is_required': True}))
        response = self.submit(self.paired_custom_id(), [labelled('winner', value=str(self.anvil.id))])
        self.assertFalse(MatchResult.objects.exists())
        self.assertIn('Your deck', response['data']['content'])

    def test_form_too_big_for_a_modal_links_to_the_site(self):
        self.add_result_form(
            ('Your deck', GhostformQuestion.AnswerType.DECK_LINK, {}),
            ('Notes', GhostformQuestion.AnswerType.TEXT, {}),
            ('Turns', GhostformQuestion.AnswerType.NUMBER, {}),
        )
        response = self.report()
        self.assertEqual(response['data']['content'], tourney.TOO_BIG_FOR_DISCORD_MESSAGE)
        link_button = response['data']['components'][0]['components'][0]
        self.assertIn(self.tournament.code, link_button['url'])

    def test_self_scheduled_report_lists_pod_mates_and_posts_pod(self):
        self.stage.pairing_strategy = 'round_robin'
        self.stage.save()
        north = Pod.objects.create(stage=self.stage, name='North', order=1)
        south = Pod.objects.create(stage=self.stage, name='South', order=2)
        StagePlayer.objects.filter(id__in=[self.anvil.id, self.comet.id]).update(pod=north)
        StagePlayer.objects.filter(id=self.beacon.id).update(pod=south)
        Round.objects.create(stage=self.stage, order=2)

        response = self.report()
        self.assertEqual(response['data']['custom_id'], f'tourney:report-add:{self.tournament.code}')
        opponent_select = response['data']['components'][0]['component']
        self.assertEqual([option['value'] for option in opponent_select['options']], [str(self.comet.id)])

        posted = self.submit(response['data']['custom_id'], [
            labelled('opponent', values=[str(self.comet.id)]),
            labelled('winner', value='them'),
            labelled('my_score', value='1'),
            labelled('their_score', value='3'),
        ])
        self.assertEqual(
            posted['data']['content'], '**Spring Open** · Swiss · Round 2 · North — Comet beat Anvil 3–1')


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
