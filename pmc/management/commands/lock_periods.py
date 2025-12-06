from django.core.management.base import BaseCommand
from pmc.models import LeaderboardSeasonPeriod


class Command(BaseCommand):
    help = 'Lock all periods that should be locked based on 7-day grace period'

    def handle(self, *args, **options):
        count = LeaderboardSeasonPeriod.objects.update_all_lock_statuses()
        self.stdout.write(self.style.SUCCESS(f'Locked {count} periods'))
