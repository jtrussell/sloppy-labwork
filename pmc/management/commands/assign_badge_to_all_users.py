from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from pmc.models import Badge, UserBadge


class Command(BaseCommand):
    help = 'Assign a badge to all existing users by badge PMC ID'

    def add_arguments(self, parser):
        parser.add_argument('badge_pmc_id', type=str,
                            help='PMC ID of the badge to assign')

    def handle(self, *args, **options):
        badge_pmc_id = options['badge_pmc_id']

        try:
            badge = Badge.objects.get(pmc_id=badge_pmc_id)
        except Badge.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Badge with PMC ID "{badge_pmc_id}" does not exist')
            )
            return

        users = User.objects.all()
        total_users = users.count()
        assigned_count = 0
        skipped_count = 0

        self.stdout.write(f'Assigning badge "{badge.name}" ({badge_pmc_id}) to {total_users} users...')

        for user in users:
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
                f'\nBadge assignment complete:\n'
                f'  Assigned: {assigned_count}\n'
                f'  Skipped (already had badge): {skipped_count}\n'
                f'  Total users: {total_users}'
            )
        )
