from datetime import timedelta
from unittest import mock

import requests
from django.contrib.messages import get_messages
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from . import discord_webhooks
from .models import Ladder, LadderChallenge, LadderEntry, LadderRuleViolation
from .tests import LadderTestBase


SIMPLE_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
WEBHOOK_URL = 'https://discord.com/api/webhooks/123456/secret-token'


class LadderPlayedResultTests(LadderTestBase):
    def test_lower_ranked_winner_moves_ahead(self):
        challenge = self.ladder.record_played_result(
            self.player(5), self.player(3), self.player(5), self.player(5).user)
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 5, 3, 4, 6))
        self.assertFalse(challenge.was_issued)
        self.assertEqual(challenge.status, LadderChallenge.ChallengeStatuses.COMPLETED)
        self.assertEqual(challenge.challenger, self.player(5))

    def test_higher_ranked_reporter_winning_keeps_positions(self):
        self.ladder.record_played_result(
            self.player(3), self.player(5), self.player(3), self.player(3).user)
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 3, 4, 5, 6))

    def test_tie_keeps_positions(self):
        challenge = self.ladder.record_played_result(
            self.player(5), self.player(3), None, self.player(5).user)
        self.assertTrue(challenge.match.result.is_tie())
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 3, 4, 5, 6))

    def test_players_must_be_within_range(self):
        with self.assertRaisesMessage(LadderRuleViolation, 'up to 3 places apart'):
            self.ladder.record_played_result(
                self.player(6), self.player(1), self.player(6), self.player(6).user)

    def test_existing_open_challenge_is_resolved_instead_of_duplicated(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        resolved = self.ladder.record_played_result(
            self.player(3), self.player(5), self.player(5), self.player(3).user)
        self.assertEqual(resolved.pk, challenge.pk)
        self.assertTrue(resolved.was_issued)
        self.assertEqual(self.ladder.challenges.count(), 1)
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 5, 3, 4, 6))

    def test_not_available_when_challenges_are_disabled(self):
        self.ladder.challenges_enabled = False
        self.ladder.save()
        with self.assertRaisesMessage(LadderRuleViolation, 'while challenges are enabled'):
            self.ladder.record_played_result(
                self.player(5), self.player(3), self.player(5), self.player(5).user)

    def test_outsiders_cannot_record(self):
        with self.assertRaises(PermissionDenied):
            self.ladder.record_played_result(
                self.player(5), self.player(3), self.player(5), self.player(1).user)

    def test_opponents_are_limited_to_range(self):
        self.assertEqual(
            self.ladder.get_played_result_opponents(self.player(1)),
            [self.player(2), self.player(3), self.player(4)])


@override_settings(STORAGES=SIMPLE_STORAGES)
class LadderPlayedResultViewTests(LadderTestBase):
    def test_player_records_a_played_game(self):
        self.client.force_login(self.player(5).user)
        url = reverse('pmc-pg-ladder-played-result', args=[self.playgroup.slug, self.ladder.pk])
        response = self.client.get(url)
        self.assertEqual(
            set(response.context['form'].fields['opponent'].queryset),
            {self.player(2), self.player(3), self.player(4), self.player(6)})
        self.client.post(url, {'opponent': self.player(3).pk, 'outcome': 'won'})
        self.assertEqual(self.ranked_usernames(), self.usernames_for(1, 2, 5, 3, 4, 6))

    def test_players_not_on_the_ladder_are_sent_back(self):
        newcomer = self.create_member('newcomer')
        self.client.force_login(newcomer.user)
        response = self.client.get(
            reverse('pmc-pg-ladder-played-result', args=[self.playgroup.slug, self.ladder.pk]))
        self.assertRedirects(
            response, reverse('pmc-pg-ladder-detail', args=[self.playgroup.slug, self.ladder.pk]))

    def test_played_games_are_labelled_in_history(self):
        self.ladder.record_played_result(
            self.player(5), self.player(3), self.player(5), self.player(5).user)
        self.client.force_login(self.player(1).user)
        response = self.client.get(
            reverse('pmc-pg-ladder-detail', args=[self.playgroup.slug, self.ladder.pk]))
        self.assertContains(response, 'Played without a challenge')


@override_settings(PMC_SITE_URL='https://keychain.example.com', STORAGES=SIMPLE_STORAGES)
class LadderChallengeEmailTests(LadderTestBase):
    def setUp(self):
        super().setUp()
        self.player(3).user.email = 'player3@example.com'
        self.player(3).user.save()

    def opt_in(self, member):
        LadderEntry.objects.filter(ladder=self.ladder, member=member).update(email_on_challenge=True)

    def test_opted_in_defender_is_emailed_after_commit(self):
        self.opt_in(self.player(3))
        with self.captureOnCommitCallbacks(execute=True):
            self.ladder.issue_challenge(self.player(5), self.player(3))
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['player3@example.com'])
        self.assertIn('player5 challenged you on Main Ladder', email.subject)
        self.assertIn('https://keychain.example.com/pg/ladder-group/ladders/', email.alternatives[0][0])

    def test_players_who_did_not_opt_in_get_no_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.ladder.issue_challenge(self.player(5), self.player(3))
        self.assertEqual(mail.outbox, [])

    def test_email_failure_does_not_break_challenges(self):
        self.opt_in(self.player(3))
        with mock.patch('pmc.ladder_notifications.send_mail', side_effect=RuntimeError('SES is down')):
            with self.captureOnCommitCallbacks(execute=True):
                challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.assertTrue(challenge.is_pending())

    def test_switch_saves_without_reloading(self):
        self.client.force_login(self.player(3).user)
        response = self.client.post(
            reverse('pmc-pg-ladder-emails', args=[self.playgroup.slug, self.ladder.pk]),
            {'email_on_challenge': 'on'}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 204)
        self.assertIn('We will email you', response['HX-Trigger'])
        response = self.client.post(
            reverse('pmc-pg-ladder-emails', args=[self.playgroup.slug, self.ladder.pk]),
            {}, HTTP_HX_REQUEST='true')
        self.assertFalse(LadderEntry.objects.get(ladder=self.ladder, member=self.player(3)).email_on_challenge)

    def test_players_toggle_challenge_emails(self):
        self.client.force_login(self.player(3).user)
        url = reverse('pmc-pg-ladder-emails', args=[self.playgroup.slug, self.ladder.pk])
        self.client.post(url, {'email_on_challenge': 'on'})
        self.assertTrue(LadderEntry.objects.get(ladder=self.ladder, member=self.player(3)).email_on_challenge)
        self.client.post(url, {'email_on_challenge': 'off'})
        self.assertFalse(LadderEntry.objects.get(ladder=self.ladder, member=self.player(3)).email_on_challenge)

    def test_players_not_on_the_ladder_cannot_toggle(self):
        newcomer = self.create_member('newcomer')
        self.client.force_login(newcomer.user)
        response = self.client.post(
            reverse('pmc-pg-ladder-emails', args=[self.playgroup.slug, self.ladder.pk]),
            {'email_on_challenge': 'on'})
        self.assertEqual(response.status_code, 404)


class DiscordWebhookUrlTests(TestCase):
    def test_accepts_discord_webhook_urls(self):
        for url in [
            'https://discord.com/api/webhooks/123/abc-DEF_1',
            'https://discordapp.com/api/webhooks/123/abc',
            'https://ptb.discord.com/api/v10/webhooks/123/abc',
            'https://canary.discord.com/api/webhooks/123/abc/',
        ]:
            self.assertTrue(discord_webhooks.is_discord_webhook_url(url), url)

    def test_rejects_other_urls(self):
        for url in [
            'http://discord.com/api/webhooks/123/abc',
            'https://discord.com.evil.example/api/webhooks/123/abc',
            'https://evil.example/discord.com/api/webhooks/123/abc',
            'https://discord.com/api/webhooks/abc/def',
            'https://169.254.169.254/latest/meta-data',
        ]:
            self.assertFalse(discord_webhooks.is_discord_webhook_url(url), url)
            with self.assertRaises(ValidationError):
                discord_webhooks.validate_discord_webhook_url(url)

    def test_escapes_markdown(self):
        self.assertEqual(discord_webhooks.escape_markdown('*bold*_x_'), r'\*bold\*\_x\_')

    def test_post_failures_are_reported_not_raised(self):
        with mock.patch('pmc.discord_webhooks.requests.post', side_effect=requests.ConnectionError):
            self.assertEqual(discord_webhooks.post_message(WEBHOOK_URL, {})[0], False)
        with mock.patch('pmc.discord_webhooks.requests.post', return_value=mock.Mock(status_code=429, text='slow down')):
            self.assertEqual(discord_webhooks.post_message(WEBHOOK_URL, {})[0], False)
        with mock.patch('pmc.discord_webhooks.requests.post', return_value=mock.Mock(status_code=204, text='')):
            self.assertEqual(discord_webhooks.post_message(WEBHOOK_URL, {}), (True, ''))

    def test_never_posts_to_non_discord_urls(self):
        with mock.patch('pmc.discord_webhooks.requests.post') as post:
            discord_webhooks.post_message('https://evil.example/hook', {})
        post.assert_not_called()


@override_settings(PMC_SITE_URL='https://keychain.example.com', STORAGES=SIMPLE_STORAGES)
class LadderDiscordWebhookTests(LadderTestBase):
    def setUp(self):
        super().setUp()
        self.ladder.discord_webhook_url = WEBHOOK_URL
        self.ladder.save()
        self.run_in_background = mock.patch(
            'pmc.discord_webhooks.run_in_background', side_effect=lambda function, *args: function(*args))
        self.run_in_background.start()
        self.post = mock.patch(
            'pmc.discord_webhooks.requests.post', return_value=mock.Mock(status_code=204, text='')).start()
        self.addCleanup(mock.patch.stopall)

    def posted_messages(self):
        return [call.kwargs['json'] for call in self.post.call_args_list]

    def test_challenge_issued_message(self):
        self.player(3).user.profile.discord_id = 987654321
        self.player(3).user.profile.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.ladder.issue_challenge(self.player(5), self.player(3))

        message = self.posted_messages()[0]
        embed = message['embeds'][0]
        self.assertEqual(self.post.call_args.args[0], WEBHOOK_URL)
        self.assertEqual(self.post.call_args.kwargs['timeout'], discord_webhooks.DISCORD_REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(message['username'], 'KeyChain')
        self.assertIn('New challenge on Main Ladder', embed['title'])
        self.assertEqual(embed['description'], '**player5** (#5) challenged **player3** (#3)')
        self.assertTrue(embed['fields'][0]['value'].startswith('<t:'))
        self.assertTrue(embed['url'].startswith('https://keychain.example.com/pg/ladder-group/ladders/'))
        self.assertEqual(embed['footer']['text'], 'Ladder Group')
        self.assertEqual(message['content'], '<@987654321>')
        self.assertEqual(message['allowed_mentions'], {'parse': [], 'users': ['987654321']})

    def test_result_message_includes_the_move(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        with self.captureOnCommitCallbacks(execute=True):
            self.ladder.record_result(challenge, self.player(5), self.player(5).user)
        embed = self.posted_messages()[-1]['embeds'][0]
        self.assertIn('Result on Main Ladder', embed['title'])
        self.assertEqual(embed['description'], '**player5** beat **player3**')
        self.assertEqual(embed['fields'][0]['value'], 'player5 moves up to #3')

    def test_forfeit_message(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.make_overdue(challenge)
        with self.captureOnCommitCallbacks(execute=True):
            self.ladder.resolve_overdue_challenges()
        self.assertEqual(
            self.posted_messages()[-1]['embeds'][0]['description'],
            '**player5** won by forfeit over **player3**')

    def test_played_game_message(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.ladder.record_played_result(
                self.player(5), self.player(3), None, self.player(5).user)
        embed = self.posted_messages()[-1]['embeds'][0]
        self.assertEqual(embed['description'], '**player5** and **player3** tied')
        self.assertIn('Played without a challenge', [field['value'] for field in embed['fields']])

    def test_names_are_markdown_escaped_and_mentions_disabled(self):
        self.player(5).nickname = '@everyone *star*'
        self.player(5).save()
        with self.captureOnCommitCallbacks(execute=True):
            self.ladder.issue_challenge(self.player(5), self.player(3))
        message = self.posted_messages()[0]
        self.assertIn(r'\*star\*', message['embeds'][0]['description'])
        self.assertEqual(message['allowed_mentions']['parse'], [])
        self.assertNotIn('content', message)

    def test_withdrawals_and_ladders_without_webhooks_post_nothing(self):
        challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        with self.captureOnCommitCallbacks(execute=True):
            self.ladder.withdraw_challenge(challenge, self.player(5).user)
        self.ladder.discord_webhook_url = ''
        self.ladder.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.ladder.issue_challenge(self.player(5), self.player(4))
        self.post.assert_not_called()

    def test_discord_outage_does_not_break_challenges(self):
        self.post.side_effect = requests.Timeout
        with self.captureOnCommitCallbacks(execute=True):
            challenge = self.ladder.issue_challenge(self.player(5), self.player(3))
        self.assertTrue(challenge.is_pending())

    def test_webhook_url_is_validated_in_ladder_settings(self):
        self.client.force_login(self.organizer.user)
        response = self.client.post(
            reverse('pmc-pg-ladder-edit', args=[self.playgroup.slug, self.ladder.pk]), {
                'name': 'Main Ladder',
                'challenges_enabled': 'on',
                'challenge_range': 3,
                'open_challenge_limit': 1,
                'response_window_days': 7,
                'discord_webhook_url': 'https://evil.example/hook',
            })
        self.assertContains(response, 'Enter a Discord webhook URL')
        self.ladder.refresh_from_db()
        self.assertEqual(self.ladder.discord_webhook_url, WEBHOOK_URL)

    def test_send_test_message(self):
        self.client.force_login(self.organizer.user)
        url = reverse('pmc-pg-ladder-discord-test', args=[self.playgroup.slug, self.ladder.pk])
        response = self.client.post(url)
        self.assertIn('Test message sent to Discord.', [str(message) for message in get_messages(response.wsgi_request)])
        self.assertIn('KeyChain is connected to Main Ladder', self.posted_messages()[0]['embeds'][0]['title'])

        self.post.return_value = mock.Mock(status_code=404, text='Unknown Webhook')
        response = self.client.post(url)
        self.assertIn('Discord rejected the message (HTTP 404).',
                      [str(message) for message in get_messages(response.wsgi_request)])

    def test_players_cannot_send_test_messages(self):
        self.client.force_login(self.player(1).user)
        response = self.client.post(
            reverse('pmc-pg-ladder-discord-test', args=[self.playgroup.slug, self.ladder.pk]))
        self.assertEqual(response.status_code, 403)
        self.post.assert_not_called()
