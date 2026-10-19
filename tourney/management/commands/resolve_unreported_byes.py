from django.core.management.base import BaseCommand
from django.db import transaction
from tourney.models import Match, MatchResult, Tournament


class Command(BaseCommand):
    help = 'Record wins for bye matches in a tournament that are missing a result'

    def add_arguments(self, parser):
        parser.add_argument('tournament_code', type=str,
                            help='Code of the tournament to fix')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without applying them',
        )

    def handle(self, *args, **options):
        tournament_code = options['tournament_code']
        dry_run = options['dry_run']

        try:
            tournament = Tournament.objects.get(code=tournament_code)
        except Tournament.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Tournament with code "{tournament_code}" does not exist')
            )
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        unresolved_byes = Match.objects.filter(
            round__stage__tournament=tournament,
            player_one__isnull=False,
            player_two__isnull=True,
            result__isnull=True,
        ).select_related('player_one__player', 'round__stage')

        self.stdout.write(
            f'Found {unresolved_byes.count()} unresolved byes in "{tournament.name}" ({tournament.code})\n'
        )

        with transaction.atomic():
            for match in unresolved_byes:
                self.stdout.write(f'  - {match}')
                if not dry_run:
                    MatchResult.objects.create(match=match, winner=match.player_one)

        self.stdout.write(self.style.SUCCESS('Bye resolution complete'))
