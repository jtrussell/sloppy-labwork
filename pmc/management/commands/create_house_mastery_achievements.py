from django.core.management.base import BaseCommand
from django.db import transaction
from pmc.models import Achievement, AchievementTier, AwardBase
from decks.models import House


class Command(BaseCommand):
    help = 'Create house mastery achievements and their tiers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without applying them',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        house_data = [
            ('043', 'Brobnar Mastery', 'Win X matches in tournaments using decks that contain Brobnar.', 'Brobnar'),
            ('044', 'Dis Mastery', 'Win X matches in tournaments using decks that contain Dis.', 'Dis'),
            ('045', 'Logos Mastery', 'Win X matches in tournaments using decks that contain Logos.', 'Logos'),
            ('046', 'Mars Mastery', 'Win X matches in tournaments using decks that contain Mars.', 'Mars'),
            ('047', 'Sanctum Mastery', 'Win X matches in tournaments using decks that contain Sanctum.', 'Sanctum'),
            ('048', 'Shadows Mastery', 'Win X matches in tournaments using decks that contain Shadows.', 'Shadows'),
            ('049', 'Untamed Mastery', 'Win X matches in tournaments using decks that contain Untamed.', 'Untamed'),
            ('050', 'Saurian Mastery', 'Win X matches in tournaments using decks that contain Saurian.', 'Saurian'),
            ('051', 'Star Alliance Mastery', 'Win X matches in tournaments using decks that contain Star Alliance.', 'Star Alliance'),
            ('052', 'Unfathomable Mastery', 'Win X matches in tournaments using decks that contain Unfathomable.', 'Unfathomable'),
            ('053', 'Ekwidon Mastery', 'Win X matches in tournaments using decks that contain Ekwidon.', 'Ekwidon'),
            ('054', 'Geistoid Mastery', 'Win X matches in tournaments using decks that contain Geistoid.', 'Geistoid'),
            ('055', 'Skyborn Mastery', 'Win X matches in tournaments using decks that contain Skyborn.', 'Skyborn'),
            ('056', 'Redemption Mastery', 'Win X matches in tournaments using decks that contain Redemption.', 'Redemption'),
        ]

        tier_data = [
            (AchievementTier.TierOptions.BRONZE, 10),
            (AchievementTier.TierOptions.SILVER, 50),
            (AchievementTier.TierOptions.GOLD, 150),
            (AchievementTier.TierOptions.ASCENSION, 500),
        ]

        image_mapping = {
            '043': {
                'Brobnar': {
                    'T1': 'usspbs',
                    'T2': 'bwh5bp',
                    'T3': 'wejpk7',
                    'T4': 'm1cypx',
                }
            },
            '044': {
                'Dis': {
                    'T1': 'vrhavg',
                    'T2': 'nciquu',
                    'T3': 'rw7yum',
                    'T4': 'qeihvc',
                }
            },
            '045': {
                'Logos': {
                    'T1': 'tgeibn',
                    'T2': 'ybgyop',
                    'T3': 'mswr90',
                    'T4': 'rodcdg',
                }
            },
            '046': {
                'Mars': {
                    'T1': 'x5n6t8',
                    'T2': 'ucvq39',
                    'T3': 'mvehmq',
                    'T4': 'ab1ccr',
                }
            },
            '047': {
                'Sanctum': {
                    'T1': 'gsrs1y',
                    'T2': 'slvjyb',
                    'T3': 'gz0ykb',
                    'T4': 'xqrzhu',
                }
            },
            '048': {
                'Shadows': {
                    'T1': 'nl7cyw',
                    'T2': 'bdcbyn',
                    'T3': 'vxyakc',
                    'T4': 'vsywjw',
                }
            },
            '049': {
                'Untamed': {
                    'T1': 'qta43e',
                    'T2': 'gknli1',
                    'T3': 'u7ik36',
                    'T4': 'nqmkow',
                }
            },
            '050': {
                'Saurian': {
                    'T1': 'rl3jlm',
                    'T2': 'hzro5j',
                    'T3': 'jfn7at',
                    'T4': 'm3nzta',
                }
            },
            '051': {
                'StarAlliance': {
                    'T1': 'shqsmr',
                    'T2': 'atn9cn',
                    'T3': 'svxgrb',
                    'T4': 'uvylnh',
                }
            },
            '052': {
                'Unfathomable': {
                    'T1': 'qdkzth',
                    'T2': 'm08qql',
                    'T3': 'm0mjek',
                    'T4': 'gdt8tt',
                }
            },
            '053': {
                'Ekwidon': {
                    'T1': 'tvsppg',
                    'T2': 'eb0f54',
                    'T3': 'vqktns',
                    'T4': 'tiq5if',
                }
            },
            '054': {
                'Geistoid': {
                    'T1': 'iihoi3',
                    'T2': 'oeg6p9',
                    'T3': 'tjqahp',
                    'T4': 'sbrlfx',
                }
            },
            '055': {
                'Skyborn': {
                    'T1': 'kcqmdc',
                    'T2': 'fu7b7a',
                    'T3': 'ys2pqh',
                    'T4': 'l1tgjb',
                }
            },
            '056': {
                'Redemption': {
                    'T1': 'rhdvct',
                    'T2': 'yk8jsj',
                    'T3': 'i3nz4d',
                    'T4': 'uygt6z',
                }
            },
        }

        base_url = 'https://res.cloudinary.com/dig7eguxo/image/upload/v1752716806'

        def get_image_url(pmc_id, house_name, tier_num, cache_buster):
            house_short = house_name.replace(' ', '')
            return f'{base_url}/{pmc_id}_{house_short}_T{tier_num}_{cache_buster}.png'

        achievements_created = 0
        tiers_created = 0

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        with transaction.atomic():
            for pmc_id, name, description, house_name in house_data:
                try:
                    house = House.objects.get(name=house_name)
                except House.DoesNotExist:
                    self.stdout.write(
                        self.style.ERROR(f'House "{house_name}" not found in database')
                    )
                    continue

                achievement, created = Achievement.objects.get_or_create(
                    pmc_id=pmc_id,
                    defaults={
                        'name': name,
                        'description': description,
                        'criteria': AwardBase.CriteriaTypeOptions.tournament_match_wins_with_house,
                        'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                        'house': house,
                    }
                )

                if created:
                    achievements_created += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'Created achievement: {name} ({pmc_id})')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'Achievement already exists: {name} ({pmc_id})')
                    )

                for tier_level, criteria_value in tier_data:
                    tier_num = tier_level + 1
                    house_short = house_name.replace(' ', '')

                    try:
                        cache_buster = image_mapping[pmc_id][house_short][f'T{tier_num}']
                        image_url = get_image_url(pmc_id, house_name, tier_num, cache_buster)
                    except KeyError:
                        self.stdout.write(
                            self.style.ERROR(f'Missing image mapping for {pmc_id} {house_name} T{tier_num}')
                        )
                        continue

                    tier, tier_created = AchievementTier.objects.get_or_create(
                        achievement=achievement,
                        tier=tier_level,
                        defaults={
                            'criteria_value': criteria_value,
                            'src': image_url,
                        }
                    )

                    if tier_created:
                        tiers_created += 1
                        tier_name = tier.get_tier_display()
                        self.stdout.write(
                            self.style.SUCCESS(f'  Created tier: {tier_name} (value: {criteria_value})')
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f'  Tier already exists: {tier.get_tier_display()}')
                        )

            if dry_run:
                raise transaction.TransactionManagementError("Dry run - rolling back transaction")

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary:\n'
                f'Achievements created: {achievements_created}\n'
                f'Tiers created: {tiers_created}'
            )
        )