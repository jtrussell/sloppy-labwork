from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, Exists, OuterRef
from django.db.models.functions import Lower


class Command(BaseCommand):
    help = 'Lowercase stored email addresses and report records that need manual attention'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Write changes to the database (default is a dry run)',
        )

    def handle(self, *args, **options):
        should_apply = options['apply']
        if not should_apply:
            self.stdout.write(self.style.WARNING(
                'DRY RUN MODE - No changes will be made'))

        has_collisions = self.report_case_collisions()
        self.report_users_without_verified_email_address()
        self.report_unverified_primary_email_addresses()

        mixed_case_users = User.objects.exclude(email=Lower('email'))
        mixed_case_email_addresses = EmailAddress.objects.exclude(
            email=Lower('email'))
        self.stdout.write(
            f'Users with mixed-case email: {mixed_case_users.count()}')
        self.stdout.write(
            f'EmailAddress rows with mixed-case email: {mixed_case_email_addresses.count()}')

        if not should_apply:
            return

        if has_collisions:
            raise CommandError(
                'Resolve the case collisions above before applying.')

        with transaction.atomic():
            updated_user_count = mixed_case_users.update(email=Lower('email'))
            updated_email_address_count = mixed_case_email_addresses.update(
                email=Lower('email'))

        self.stdout.write(self.style.SUCCESS(
            f'Lowercased {updated_user_count} user emails and '
            f'{updated_email_address_count} EmailAddress rows'))

    def report_case_collisions(self):
        user_email_collisions = (
            User.objects.exclude(email='')
            .values(normalized_email=Lower('email'))
            .annotate(user_count=Count('id'))
            .filter(user_count__gt=1)
        )
        same_user_email_address_collisions = (
            EmailAddress.objects
            .values('user_id', normalized_email=Lower('email'))
            .annotate(row_count=Count('id'))
            .filter(row_count__gt=1)
        )
        verified_email_address_collisions = (
            EmailAddress.objects.filter(verified=True)
            .values(normalized_email=Lower('email'))
            .annotate(user_count=Count('user_id', distinct=True))
            .filter(user_count__gt=1)
        )

        has_collisions = False
        for collision in user_email_collisions:
            has_collisions = True
            self.stdout.write(self.style.ERROR(
                f'Users share email ignoring case: {collision["normalized_email"]}'))
        for collision in same_user_email_address_collisions:
            has_collisions = True
            self.stdout.write(self.style.ERROR(
                f'User {collision["user_id"]} has EmailAddress rows differing only by case: '
                f'{collision["normalized_email"]}'))
        for collision in verified_email_address_collisions:
            has_collisions = True
            self.stdout.write(self.style.ERROR(
                f'Verified EmailAddress shared across users ignoring case: '
                f'{collision["normalized_email"]}'))
        return has_collisions

    def report_users_without_verified_email_address(self):
        verified_matching_email_address = EmailAddress.objects.filter(
            user_id=OuterRef('pk'),
            email__iexact=OuterRef('email'),
            verified=True,
        )
        users = (
            User.objects.exclude(email='')
            .exclude(Exists(verified_matching_email_address))
            .order_by('pk')
        )
        for user in users:
            self.stdout.write(self.style.WARNING(
                f'User {user.pk} ({user.username}) has no verified EmailAddress '
                f'matching their email: {user.email}'))

    def report_unverified_primary_email_addresses(self):
        email_addresses = (
            EmailAddress.objects.filter(primary=True, verified=False)
            .select_related('user')
            .order_by('user_id')
        )
        for email_address in email_addresses:
            self.stdout.write(self.style.WARNING(
                f'User {email_address.user_id} ({email_address.user.username}) has an '
                f'unverified primary EmailAddress: {email_address.email}'))
