import io
import re
from datetime import date, timedelta

from allauth.account.forms import SignupForm
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from django.contrib.auth.models import Permission, User
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from pmc.models import (
    AwardBase, AwardCredit, Badge, Event, EventResult, Leaderboard, LeaderboardSeason,
    LeaderboardSeasonPeriod, PlayerRank, Playgroup, PlaygroupMember, RankingPoints, Trophy,
    UserBadge, UserTrophy,
)
from tourney.models import Player, Tournament, TournamentAdmin
from trade_secrets.models import Session as TradeSecretsSession, SessionTemplate
from user_profile.management.commands import merge_users
from .forms import EditUsernameForm


def create_user_with_verified_email(username, email):
    user = User.objects.create_user(username=username, email=email)
    EmailAddress.objects.create(
        user=user, email=email, verified=True, primary=True)
    return user


class EditUsernameFormTests(TestCase):
    def setUp(self):
        self.user = create_user_with_verified_email('Player', 'player@example.com')
        self.other_user = create_user_with_verified_email('Rival', 'rival@example.com')

    def build_form(self, **overrides):
        data = {'username': self.user.username, 'email': self.user.email}
        data.update(overrides)
        return EditUsernameForm(data, instance=self.user)

    def test_rejects_username_differing_only_by_case_from_another_user(self):
        form = self.build_form(username='rIVAL')
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)

    def test_allows_changing_casing_of_own_username(self):
        form = self.build_form(username='PLAYER')
        self.assertTrue(form.is_valid())
        form.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'PLAYER')

    def test_requires_email(self):
        form = self.build_form(email='')
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_lowercases_email(self):
        form = self.build_form(email='New.Address@Example.com')
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['email'], 'new.address@example.com')

    def test_does_not_reveal_that_another_user_has_the_email(self):
        form = self.build_form(email='RIVAL@example.com')
        self.assertTrue(form.is_valid())

    def test_save_does_not_write_user_email(self):
        form = self.build_form(email='new@example.com')
        self.assertTrue(form.is_valid())
        form.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'player@example.com')

    def test_initial_email_comes_from_instance(self):
        form = EditUsernameForm(instance=self.user)
        self.assertEqual(form.initial['email'], 'player@example.com')


class EmailChangeFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = create_user_with_verified_email('Player', 'player@example.com')
        self.client.force_login(self.user)

    def post_profile(self, **overrides):
        data = {
            'username': self.user.username,
            'email': self.user.email,
            'theme': self.user.profile.theme,
        }
        data.update(overrides)
        return self.client.post(reverse('profile'), data)

    def extract_confirmation_key(self, message):
        return re.search(r'/accounts/confirm-email/([^/]+)/', message.body).group(1)

    def test_changing_email_sends_verification_without_switching_email(self):
        response = self.post_profile(email='New@Example.com')
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'player@example.com')
        pending_email_address = EmailAddress.objects.get_new(self.user)
        self.assertEqual(pending_email_address.email, 'new@example.com')
        self.assertFalse(pending_email_address.verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['new@example.com'])

    def test_changing_only_email_casing_does_not_start_email_change(self):
        self.post_profile(email='PLAYER@example.com')
        self.assertIsNone(EmailAddress.objects.get_new(self.user))
        self.assertEqual(len(mail.outbox), 0)

    def test_username_change_preserves_casing(self):
        self.post_profile(username='PlayerOne')
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'PlayerOne')

    def test_confirming_new_email_switches_user_email_and_removes_old_address(self):
        self.post_profile(email='new@example.com')
        confirmation_key = self.extract_confirmation_key(mail.outbox[0])
        self.client.post(reverse('account_confirm_email', args=[confirmation_key]))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.com')
        self.assertEqual(
            list(EmailAddress.objects.filter(user=self.user).values_list('email', 'verified', 'primary')),
            [('new@example.com', True, True)],
        )

    def test_confirming_email_verified_by_another_user_fails(self):
        create_user_with_verified_email('Rival', 'rival@example.com')
        self.post_profile(email='rival@example.com')
        confirmation_key = self.extract_confirmation_key(mail.outbox[0])
        self.client.post(reverse('account_confirm_email', args=[confirmation_key]))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'player@example.com')
        self.assertFalse(EmailAddress.objects.get_new(self.user).verified)


class SignupUsernameCasingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_signup_rejects_username_differing_only_by_case(self):
        User.objects.create_user(username='Player', email='player@example.com')
        form = SignupForm(data={
            'email': 'someone@example.com',
            'username': 'pLAYER',
            'password1': 'a-strong-password-123',
            'password2': 'a-strong-password-123',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)

    def test_signup_preserves_username_casing(self):
        self.client.post(reverse('account_signup'), {
            'email': 'someone@example.com',
            'username': 'MixedCase',
            'password1': 'a-strong-password-123',
            'password2': 'a-strong-password-123',
        })
        self.assertTrue(User.objects.filter(username='MixedCase').exists())


class NormalizeUserEmailsCommandTests(TestCase):
    def run_command(self, *args):
        output = io.StringIO()
        call_command('normalize_user_emails', *args, stdout=output)
        return output.getvalue()

    def test_dry_run_reports_without_changing_data(self):
        user = create_user_with_verified_email('Player', 'Player@example.com')
        output = self.run_command()
        self.assertIn('DRY RUN', output)
        self.assertIn('Users with mixed-case email: 1', output)
        user.refresh_from_db()
        self.assertEqual(user.email, 'Player@example.com')

    def test_apply_lowercases_user_and_email_address_rows(self):
        user = create_user_with_verified_email('Player', 'Player@Example.com')
        self.run_command('--apply')
        user.refresh_from_db()
        self.assertEqual(user.email, 'player@example.com')
        self.assertEqual(EmailAddress.objects.get(user=user).email, 'player@example.com')

    def test_apply_refuses_when_email_addresses_collide_by_case(self):
        user = User.objects.create_user(username='Player', email='player@example.com')
        EmailAddress.objects.create(user=user, email='player@example.com', verified=True, primary=True)
        EmailAddress.objects.create(user=user, email='Player@Example.com', verified=False, primary=False)
        with self.assertRaises(CommandError):
            self.run_command('--apply')
        self.assertTrue(EmailAddress.objects.filter(email='Player@Example.com').exists())

    def test_reports_users_without_verified_matching_email_address(self):
        User.objects.create_user(username='Legacy', email='legacy@example.com')
        output = self.run_command()
        self.assertIn('Legacy', output)
        self.assertIn('no verified EmailAddress', output)

    def test_reports_unverified_primary_email_addresses(self):
        user = User.objects.create_user(username='Pending', email='pending@example.com')
        EmailAddress.objects.create(user=user, email='pending@example.com', verified=False, primary=True)
        output = self.run_command()
        self.assertIn('unverified primary EmailAddress: pending@example.com', output)


class CaseInsensitiveIdentityIndexTests(TestCase):
    def test_rejects_username_differing_only_by_case(self):
        User.objects.create_user(username='Player')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username='pLAYER')

    def test_rejects_email_differing_only_by_case(self):
        User.objects.create_user(username='first', email='player@example.com')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username='second', email='PLAYER@example.com')

    def test_allows_multiple_users_with_blank_email(self):
        User.objects.create_user(username='first', email='')
        User.objects.create_user(username='second', email='')
        self.assertEqual(User.objects.filter(email='').count(), 2)


class MergeUsersCommandTests(TestCase):
    def setUp(self):
        self.primary = create_user_with_verified_email('Player', 'primary@example.com')
        self.secondary = create_user_with_verified_email('PlayerDuplicate', 'secondary@example.com')
        self.playgroup = Playgroup.objects.create(name='Merge Group', slug='merge-group')

    def run_command(self, *args):
        output = io.StringIO()
        call_command(
            'merge_users',
            '--primary', str(self.primary.pk),
            '--secondary', str(self.secondary.pk),
            *args,
            stdout=output,
        )
        return output.getvalue()

    def create_event(self, name='Event'):
        return Event.objects.create(name=name, start_date=date(2025, 1, 1), player_count=4)

    def create_ranking_context(self):
        leaderboard = Leaderboard.objects.create(
            name='Monthly', sort_order=1,
            period_frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH)
        season = LeaderboardSeason.objects.create(name='Season')
        period = LeaderboardSeasonPeriod.objects.create(
            name='January', start_date=date(2025, 1, 1), season=season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH, is_locked=True)
        return leaderboard, period

    def create_player_rank(self, user, leaderboard, period, rank, playgroup=None):
        return PlayerRank.objects.create(
            user=user, leaderboard=leaderboard, period=period, playgroup=playgroup, rank=rank)

    def create_trophy(self, pmc_id, criteria):
        return Trophy.objects.create(
            pmc_id=pmc_id, name=f'Trophy {pmc_id}', criteria=criteria,
            reward_category=AwardBase.RewardCategoryOptions.TASK, mode=AwardBase.ModeOptions.ANY)

    def create_badge(self, pmc_id):
        return Badge.objects.create(
            pmc_id=pmc_id, name=f'Badge {pmc_id}',
            reward_category=AwardBase.RewardCategoryOptions.TASK, mode=AwardBase.ModeOptions.ANY)

    def test_dry_run_reports_without_changing_data(self):
        EventResult.objects.create(user=self.secondary, event=self.create_event())
        output = self.run_command()
        self.assertIn('DRY RUN', output)
        self.assertIn('move: pmc.EventResult.user (1)', output)
        self.assertTrue(User.objects.filter(pk=self.secondary.pk).exists())
        self.assertTrue(EventResult.objects.filter(user=self.secondary).exists())

    def test_apply_deletes_secondary_and_its_discarded_records(self):
        self.secondary.pmc_profile.tagline = 'secondary tagline'
        self.secondary.pmc_profile.save()
        self.primary.pmc_profile.tagline = 'primary tagline'
        self.primary.pmc_profile.save()
        output = self.run_command('--apply')
        self.assertIn('secondary tagline', output)
        self.assertIn('secondary@example.com', output)
        self.assertFalse(User.objects.filter(pk=self.secondary.pk).exists())
        self.assertFalse(EmailAddress.objects.filter(email='secondary@example.com').exists())
        self.primary.refresh_from_db()
        self.assertEqual(self.primary.pmc_profile.tagline, 'primary tagline')
        self.assertEqual(self.primary.email, 'primary@example.com')

    def test_moves_event_results_with_ranking_points(self):
        result = EventResult.objects.create(user=self.secondary, event=self.create_event())
        RankingPoints.objects.create(result=result, points=10)
        self.run_command('--apply')
        result.refresh_from_db()
        self.assertEqual(result.user, self.primary)
        self.assertEqual(RankingPoints.objects.get(result=result).points, 10)

    def test_moves_tournament_players_and_award_credits(self):
        tournament = Tournament.objects.create(name='Cup', owner=self.primary)
        player = Player.objects.create(user=self.secondary, tournament=tournament)
        AwardCredit.objects.create(
            user=self.secondary, criteria=AwardBase.CriteriaTypeOptions.events, amount=2)
        self.run_command('--apply')
        player.refresh_from_db()
        self.assertEqual(player.user, self.primary)
        self.assertEqual(AwardCredit.objects.get().user, self.primary)

    def test_moves_trade_secrets_sessions_and_deletes_sessions_between_the_two(self):
        triad = SessionTemplate.objects.get(system_key='triad')
        opponent = User.objects.create_user(username='Opponent')
        shared_session = TradeSecretsSession.objects.create(template=triad, host=self.primary, guest=self.secondary)
        other_session = TradeSecretsSession.objects.create(template=triad, host=self.secondary, guest=opponent)
        merge_users.merge_users(self.primary, self.secondary)
        self.assertFalse(TradeSecretsSession.objects.filter(pk=shared_session.pk).exists())
        other_session.refresh_from_db()
        self.assertEqual(other_session.host, self.primary)

    def test_moves_social_account_and_its_token_still_resolves(self):
        social_app = SocialApp.objects.create(
            provider='discord', name='Discord', client_id='id', secret='secret')
        social_account = SocialAccount.objects.create(
            user=self.secondary, provider='discord', uid='12345')
        SocialToken.objects.create(app=social_app, account=social_account, token='token')
        self.run_command('--apply')
        social_account.refresh_from_db()
        self.assertEqual(social_account.user, self.primary)
        self.assertEqual(SocialToken.objects.get(account__user=self.primary).token, 'token')

    def test_merges_overlapping_badges_keeping_earliest_award_date(self):
        shared_badge = self.create_badge('B1')
        secondary_only_badge = self.create_badge('B2')
        primary_badge = UserBadge.objects.create(user=self.primary, badge=shared_badge)
        secondary_badge = UserBadge.objects.create(user=self.secondary, badge=shared_badge)
        earlier = timezone.now() - timedelta(days=30)
        UserBadge.objects.filter(pk=secondary_badge.pk).update(date_awarded=earlier)
        UserBadge.objects.create(user=self.secondary, badge=secondary_only_badge)
        self.run_command('--apply')
        primary_badge.refresh_from_db()
        self.assertEqual(primary_badge.date_awarded, earlier)
        self.assertEqual(
            set(UserBadge.objects.filter(user=self.primary).values_list('badge__pmc_id', flat=True)),
            {'B1', 'B2'})

    def test_merges_manual_trophies_and_drops_computed_ones(self):
        manual_trophy = self.create_trophy('T1', AwardBase.CriteriaTypeOptions.manually_awarded)
        computed_trophy = self.create_trophy('T2', AwardBase.CriteriaTypeOptions.events)
        primary_trophy = UserTrophy.objects.create(user=self.primary, trophy=manual_trophy, amount=1)
        UserTrophy.objects.create(user=self.secondary, trophy=manual_trophy, amount=3)
        UserTrophy.objects.create(user=self.secondary, trophy=computed_trophy, amount=5)
        self.run_command('--apply')
        primary_trophy.refresh_from_db()
        self.assertEqual(primary_trophy.amount, 3)
        self.assertFalse(UserTrophy.objects.filter(trophy=computed_trophy).exists())
        self.assertEqual(UserTrophy.objects.count(), 1)

    def test_merges_playgroup_memberships_keeping_staff_access(self):
        other_playgroup = Playgroup.objects.create(name='Other Group', slug='other-group')
        PlaygroupMember.objects.create(playgroup=self.playgroup, user=self.primary)
        PlaygroupMember.objects.create(playgroup=self.playgroup, user=self.secondary, is_staff=True)
        PlaygroupMember.objects.create(playgroup=other_playgroup, user=self.secondary)
        self.run_command('--apply')
        self.assertTrue(PlaygroupMember.objects.get(playgroup=self.playgroup, user=self.primary).is_staff)
        self.assertTrue(PlaygroupMember.objects.filter(playgroup=other_playgroup, user=self.primary).exists())
        self.assertEqual(PlaygroupMember.objects.count(), 2)

    def test_folds_player_ranks_keeping_the_better_rank(self):
        leaderboard, period = self.create_ranking_context()
        self.create_player_rank(self.primary, leaderboard, period, rank=5, playgroup=self.playgroup)
        self.create_player_rank(self.secondary, leaderboard, period, rank=2, playgroup=self.playgroup)
        self.create_player_rank(self.primary, leaderboard, period, rank=1)
        self.create_player_rank(self.secondary, leaderboard, period, rank=4)
        self.run_command('--apply')
        self.assertEqual(PlayerRank.objects.filter(user=self.primary).count(), 2)
        self.assertEqual(PlayerRank.objects.get(playgroup=self.playgroup).rank, 2)
        self.assertEqual(PlayerRank.objects.get(playgroup__isnull=True).rank, 1)

    def test_drops_admin_role_on_tournaments_the_primary_owns_or_admins(self):
        owned_tournament = Tournament.objects.create(name='Owned', owner=self.primary)
        co_admin_tournament = Tournament.objects.create(name='Co-admin')
        other_tournament = Tournament.objects.create(name='Other')
        TournamentAdmin.objects.create(user=self.secondary, tournament=owned_tournament)
        TournamentAdmin.objects.create(user=self.primary, tournament=co_admin_tournament)
        TournamentAdmin.objects.create(user=self.secondary, tournament=co_admin_tournament)
        TournamentAdmin.objects.create(user=self.secondary, tournament=other_tournament)
        self.run_command('--apply')
        self.assertEqual(
            set(TournamentAdmin.objects.values_list('tournament__name', 'user_id')),
            {('Co-admin', self.primary.pk), ('Other', self.primary.pk)})

    def test_aborts_when_both_users_have_a_result_in_the_same_event(self):
        event = self.create_event()
        EventResult.objects.create(user=self.primary, event=event)
        EventResult.objects.create(user=self.secondary, event=event)
        with self.assertRaises(CommandError):
            self.run_command('--apply')
        self.assertTrue(User.objects.filter(pk=self.secondary.pk).exists())
        self.assertEqual(EventResult.objects.filter(user=self.secondary).count(), 1)

    def test_aborts_when_both_users_play_in_the_same_tournament(self):
        tournament = Tournament.objects.create(name='Cup')
        Player.objects.create(user=self.primary, tournament=tournament)
        Player.objects.create(user=self.secondary, tournament=tournament)
        with self.assertRaises(CommandError):
            self.run_command('--apply')
        self.assertTrue(User.objects.filter(pk=self.secondary.pk).exists())
        self.assertEqual(Player.objects.filter(user=self.secondary).count(), 1)

    def test_reports_but_does_not_copy_access(self):
        self.secondary.is_staff = True
        self.secondary.save()
        self.secondary.user_permissions.add(Permission.objects.get(codename='change_user'))
        output = self.run_command('--apply')
        self.assertIn('is_staff=True', output)
        self.assertIn('auth.change_user', output)
        self.primary.refresh_from_db()
        self.assertFalse(self.primary.is_staff)
        self.assertFalse(self.primary.user_permissions.exists())

    def test_rejects_same_or_missing_users(self):
        with self.assertRaises(CommandError):
            call_command('merge_users', '--primary', str(self.primary.pk),
                         '--secondary', str(self.primary.pk), stdout=io.StringIO())
        with self.assertRaises(CommandError):
            call_command('merge_users', '--primary', str(self.primary.pk),
                         '--secondary', '999999', stdout=io.StringIO())

    def test_every_user_relation_has_a_merge_rule(self):
        self.assertEqual(merge_users.find_unhandled_user_relations(), [])

    def test_detects_relations_without_a_merge_rule(self):
        handled_relations = merge_users.HANDLED_RELATIONS - {('pmc.EventResult', 'user')}
        self.assertEqual(
            merge_users.find_unhandled_user_relations(handled_relations),
            [('pmc.EventResult', 'user')])
