import io
import re

from allauth.account.forms import SignupForm
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

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
