from django.core.management.base import BaseCommand
from pmc.models import RankingPointsMap, RankingPointsMapVersion
from datetime import date


class Command(BaseCommand):
    help = 'Sets up ranking points map versions and creates Version 2 entries'

    def handle(self, *args, **options):
        self.stdout.write('Setting up ranking points map versions...')

        version_1, v1_created = RankingPointsMapVersion.objects.get_or_create(
            effective_on=date(1900, 1, 1),
            defaults={'name': 'Version 1'}
        )
        if v1_created:
            self.stdout.write(self.style.SUCCESS(f'  Created {version_1.name}'))
        else:
            self.stdout.write(f'  {version_1.name} already exists')

        version_2, v2_created = RankingPointsMapVersion.objects.get_or_create(
            effective_on=date(2025, 12, 1),
            defaults={'name': 'Version 2'}
        )
        if v2_created:
            self.stdout.write(self.style.SUCCESS(f'  Created {version_2.name}'))
        else:
            self.stdout.write(f'  {version_2.name} already exists')

        self.stdout.write('\nAssigning existing entries to Version 1... ', ending='')
        updated_count = RankingPointsMap.objects.filter(version__isnull=True).update(version=version_1)
        self.stdout.write(self.style.SUCCESS(f'{updated_count} entries updated'))

        self.stdout.write('\nCreating Version 2 ranking points map entries...')

        v2_entries = [
            # 4 players
            {'max_players': 4, 'finishing_position': 1, 'points': 1200},
            {'max_players': 4, 'finishing_position': 2, 'points': 900},
            {'max_players': 4, 'finishing_position': 3, 'points': 675},

            # 8 players
            {'max_players': 8, 'finishing_position': 1, 'points': 1225},
            {'max_players': 8, 'finishing_position': 2, 'points': 980},
            {'max_players': 8, 'finishing_position': 3, 'points': 784},
            {'max_players': 8, 'finishing_position': 5, 'points': 627},

            # 16 players
            {'max_players': 16, 'finishing_position': 1, 'points': 1275},
            {'max_players': 16, 'finishing_position': 2, 'points': 1020},
            {'max_players': 16, 'finishing_position': 3, 'points': 816},
            {'max_players': 16, 'finishing_position': 5, 'points': 653},
            {'max_players': 16, 'finishing_position': 9, 'points': 522},

            # 32 players
            {'max_players': 32, 'finishing_position': 1, 'points': 1375},
            {'max_players': 32, 'finishing_position': 2, 'points': 1100},
            {'max_players': 32, 'finishing_position': 3, 'points': 880},
            {'max_players': 32, 'finishing_position': 5, 'points': 704},
            {'max_players': 32, 'finishing_position': 9, 'points': 563},
            {'max_players': 32, 'finishing_position': 17, 'points': 450},

            # 64 players
            {'max_players': 64, 'finishing_position': 1, 'points': 1575},
            {'max_players': 64, 'finishing_position': 2, 'points': 1260},
            {'max_players': 64, 'finishing_position': 3, 'points': 1008},
            {'max_players': 64, 'finishing_position': 5, 'points': 806},
            {'max_players': 64, 'finishing_position': 9, 'points': 645},
            {'max_players': 64, 'finishing_position': 17, 'points': 516},
            {'max_players': 64, 'finishing_position': 33, 'points': 413},
        ]

        created_count = 0
        for entry_data in v2_entries:
            _, created = RankingPointsMap.objects.get_or_create(
                max_players=entry_data['max_players'],
                finishing_position=entry_data['finishing_position'],
                version=version_2,
                defaults={'points': entry_data['points']}
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f'  Created {created_count} new entries for Version 2'))

        if created_count > 0:
            self.stdout.write(self.style.SUCCESS(
                f'\nRanking points map setup complete! Version 2 will take effect on {version_2.effective_on}.'
            ))
        else:
            self.stdout.write(
                f'\nAll Version 2 entries already exist. Version 2 effective on {version_2.effective_on}.'
            )
