from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from pmc.models import Badge, UserBadge


class Command(BaseCommand):
    help = 'Assign a badge to a list of users by username'

    def add_arguments(self, parser):
        parser.add_argument('badge_pmc_id', type=str,
                            help='PMC ID of the badge to assign')
        parser.add_argument('usernames', nargs='+', type=str,
                            help='Usernames to assign the badge to')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without applying them',
        )

    def handle(self, *args, **options):
        badge_pmc_id = options['badge_pmc_id']
        usernames = options['usernames']
        dry_run = options['dry_run']

        try:
            badge = Badge.objects.get(pmc_id=badge_pmc_id)
        except Badge.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Badge with PMC ID "{badge_pmc_id}" does not exist')
            )
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        self.stdout.write(f'Assigning badge "{badge.name}" ({badge_pmc_id}) to {len(usernames)} users...\n')

        assigned_count = 0
        skipped_count = 0
        not_found = []

        for username in usernames:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                not_found.append(username)
                continue

            if dry_run:
                exists = UserBadge.objects.filter(user=user, badge=badge).exists()
                if exists:
                    skipped_count += 1
                else:
                    assigned_count += 1
            else:
                _, created = UserBadge.objects.get_or_create(
                    user=user,
                    badge=badge
                )
                if created:
                    assigned_count += 1
                else:
                    skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Badge assignment complete:\n'
                f'  Assigned: {assigned_count}\n'
                f'  Skipped (already had badge): {skipped_count}'
            )
        )

        if not_found:
            self.stdout.write(
                self.style.WARNING(f'  Users not found: {len(not_found)}')
            )
            for username in not_found:
                self.stdout.write(self.style.WARNING(f'    - {username}'))
