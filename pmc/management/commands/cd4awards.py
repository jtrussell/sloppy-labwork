from django.core.management.base import BaseCommand
from django.db import transaction
from pmc.models import Achievement, AchievementTier, Trophy, AwardBase


class Command(BaseCommand):
    help = 'Create CD4 awards: Premier Pro achievement and leaderboard trophies'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without applying them',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        achievement_data = {
            'pmc_id': '074',
            'name': 'Premier Pro',
            'description': 'Participate in X Premier Tournaments.',
            'criteria': AwardBase.CriteriaTypeOptions.participate_in_premier_tournament,
            'reward_category': AwardBase.RewardCategoryOptions.PARTICIPATION,
            'mode': AwardBase.ModeOptions.ANY,
            'sort_order': 74,
        }

        tier_data = [
            (AchievementTier.TierOptions.BRONZE, 2, 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547507/074_PremierPro_T1_zjxvqy.png'),
            (AchievementTier.TierOptions.SILVER, 8, 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547505/074_PremierPro_T2_llc6va.png'),
            (AchievementTier.TierOptions.GOLD, 20, 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547505/074_PremierPro_T3_tq6cv6.png'),
            (AchievementTier.TierOptions.ASCENSION, 50, 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547505/074_PremierPro_T4_nmav6v.png'),
        ]

        trophy_data = [
            {
                'pmc_id': '073',
                'name': 'KFC Open Champion',
                'description': 'Win a KeyForge Celebration Open tournament.',
                'criteria': AwardBase.CriteriaTypeOptions.manually_awarded,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 73,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1763731272/073_OpenChampion_m6lkiv.png',
            },
            {
                'pmc_id': '075',
                'name': 'Playgroup Season Champion',
                'description': 'Finish in 1st place in a playgroup\'s seasonal leaderboard.',
                'criteria': AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_first_place,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 75,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547505/075_PS_Champion_ncobkp.png',
            },
            {
                'pmc_id': '076',
                'name': 'Playgroup Season Runner-Up',
                'description': 'Finish in 2nd place in a playgroup\'s seasonal leaderboard.',
                'criteria': AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_second_place,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 76,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547505/076_PS_RunnerUp_ledddc.png',
            },
            {
                'pmc_id': '077',
                'name': 'Playgroup Season Third Place',
                'description': 'Finish in 3rd place in a playgroup\'s seasonal leaderboard.',
                'criteria': AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_third_place,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 77,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547506/077_PS_Third_isy6y8.png',
            },
            {
                'pmc_id': '078',
                'name': 'Playgroup Season Top 5',
                'description': 'Finish in 4th or 5th place in a playgroup\'s seasonal leaderboard (which has a minimum of 10 ranked players).',
                'criteria': AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_top_five,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 78,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547506/078_PS_Top5_eoatde.png',
            },
            {
                'pmc_id': '079',
                'name': 'Playgroup Season Top 10',
                'description': 'Finish in 6th through 10th place in a playgroup\'s seasonal leaderboard (which has a minimum of 20 ranked players).',
                'criteria': AwardBase.CriteriaTypeOptions.playgroup_leaderboard_season_top_ten,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 79,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547506/079_PS_Top10_tjgz05.png',
            },
            {
                'pmc_id': '080',
                'name': 'Global Season Champion',
                'description': 'Finish in 1st place in a global season leaderboard.',
                'criteria': AwardBase.CriteriaTypeOptions.global_leaderboard_season_first_place,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 80,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547506/080_GS_Champion_ungndl.png',
            },
            {
                'pmc_id': '081',
                'name': 'Global Season Top 10',
                'description': 'Finish in 2nd through 10th place in a global season leaderboard.',
                'criteria': AwardBase.CriteriaTypeOptions.global_leaderboard_season_top_ten,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 81,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547506/081_GS_Top10_ks4dk4.png',
            },
            {
                'pmc_id': '082',
                'name': 'Global Season Top 50',
                'description': 'Finish in 11th through 50th place in a global season leaderboard.',
                'criteria': AwardBase.CriteriaTypeOptions.global_leaderboard_season_top_fifty,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 82,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547508/082_GS_Top50_hqaact.png',
            },
            {
                'pmc_id': '083',
                'name': 'Global Season Top 100',
                'description': 'Finish in 51st through 100th place in a global season leaderboard.',
                'criteria': AwardBase.CriteriaTypeOptions.global_leaderboard_season_top_one_hundred,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 83,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547508/083_GS_Top100_gy6mef.png',
            },
            {
                'pmc_id': '084',
                'name': 'Global Monthly Champion',
                'description': 'Finish in 1st place in a global monthly leaderboard.',
                'criteria': AwardBase.CriteriaTypeOptions.global_leaderboard_monthly_first_place,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 84,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547517/084_GM_Champion_h9ndta.png',
            },
            {
                'pmc_id': '085',
                'name': 'Global Monthly Top 10',
                'description': 'Finish in 2nd through 10th place in a global monthly leaderboard.',
                'criteria': AwardBase.CriteriaTypeOptions.global_leaderboard_monthly_top_ten,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 85,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547517/085_GM_Top10_r9gksu.png',
            },
            {
                'pmc_id': '086',
                'name': 'Global Monthly Top 25',
                'description': 'Finish in 11th through 25th place in a global monthly leaderboard.',
                'criteria': AwardBase.CriteriaTypeOptions.global_leaderboard_monthly_top_twenty_five,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 86,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547517/086_GM_Top25_smh2hu.png',
            },
            {
                'pmc_id': '087',
                'name': 'Global Monthly Top 50',
                'description': 'Finish in 26th through 50th place in a global monthly leaderboard.',
                'criteria': AwardBase.CriteriaTypeOptions.global_leaderboard_monthly_top_fifty,
                'reward_category': AwardBase.RewardCategoryOptions.SKILL,
                'mode': AwardBase.ModeOptions.ANY,
                'criteria_value': 1,
                'sort_order': 87,
                'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1764547517/087_GM_Top50_hxirwt.png',
            },
        ]

        achievements_created = 0
        tiers_created = 0
        trophies_created = 0

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        with transaction.atomic():
            achievement, created = Achievement.objects.get_or_create(
                pmc_id=achievement_data['pmc_id'],
                defaults={
                    'name': achievement_data['name'],
                    'description': achievement_data['description'],
                    'criteria': achievement_data['criteria'],
                    'reward_category': achievement_data['reward_category'],
                    'mode': achievement_data['mode'],
                    'sort_order': achievement_data['sort_order'],
                    'is_hidden': True,
                }
            )

            if created:
                achievements_created += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Created achievement: {achievement_data["name"]} ({achievement_data["pmc_id"]})'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'Achievement already exists: {achievement_data["name"]} ({achievement_data["pmc_id"]})'
                    )
                )

            for tier_level, criteria_value, src in tier_data:
                tier, tier_created = AchievementTier.objects.get_or_create(
                    achievement=achievement,
                    tier=tier_level,
                    defaults={
                        'criteria_value': criteria_value,
                        'src': src,
                    }
                )

                if tier_created:
                    tiers_created += 1
                    tier_name = tier.get_tier_display()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  Created tier: {tier_name} (value: {criteria_value})'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  Tier already exists: {tier.get_tier_display()}'
                        )
                    )

            for trophy_info in trophy_data:
                trophy, created = Trophy.objects.get_or_create(
                    pmc_id=trophy_info['pmc_id'],
                    defaults={
                        'name': trophy_info['name'],
                        'description': trophy_info['description'],
                        'criteria': trophy_info['criteria'],
                        'reward_category': trophy_info['reward_category'],
                        'mode': trophy_info['mode'],
                        'criteria_value': trophy_info['criteria_value'],
                        'sort_order': trophy_info['sort_order'],
                        'src': trophy_info['src'],
                        'is_hidden': True,
                    }
                )

                if created:
                    trophies_created += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Created trophy: {trophy_info["name"]} ({trophy_info["pmc_id"]})'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Trophy already exists: {trophy_info["name"]} ({trophy_info["pmc_id"]})'
                        )
                    )

            if dry_run:
                raise transaction.TransactionManagementError("Dry run - rolling back transaction")

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary:\n'
                f'Achievements created: {achievements_created}\n'
                f'Achievement tiers created: {tiers_created}\n'
                f'Trophies created: {trophies_created}'
            )
        )
