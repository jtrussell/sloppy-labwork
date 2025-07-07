from django.core.management.base import BaseCommand
from pmc.models import LevelBreakpoint, EventFormat, Leaderboard
from pmc.models import LeaderboardSeason, LeaderboardSeasonPeriod, Avatar, Background, AvatarCategory
from pmc.models import BackgroundCategory, PlaygroupType, RankingPointsMap
from decks.models import Set, House
from datetime import date


class Command(BaseCommand):
    help = 'Setups up basic PMC data for development and testing'

    def handle(self, *args, **options):
        self.stdout.write('Creating level breakpoints... ', ending='')
        self.make_levels()
        self.stdout.write(
            self.style.SUCCESS('OK')
        )

        self.stdout.write('Creating event formats... ', ending='')
        self.make_events_formats()
        self.stdout.write(
            self.style.SUCCESS('OK')
        )

        self.stdout.write(
            'Making leaderboards, seasons, periods... ', ending='')
        self.make_leaderboards()
        self.stdout.write(
            self.style.SUCCESS('OK')
        )

        self.stdout.write(
            'Making ranking points maps... ', ending='')
        self.make_ranking_points_map()
        self.stdout.write(
            self.style.SUCCESS('OK')
        )

        self.stdout.write('Making avatars... ', ending='')
        self.make_avatars()
        self.stdout.write(self.style.SUCCESS('OK'))

        self.stdout.write('Making backgrounds... ', ending='')
        self.make_backgrounds()
        self.stdout.write(self.style.SUCCESS('OK'))

        self.stdout.write('Making playgroup types... ', ending='')
        self.make_playgroup_types()
        self.stdout.write(self.style.SUCCESS('OK'))

    def make_sets(self):
        Set.objects.get_or_create(
            id=341, defaults={'name': 'Call of the Archons'})
        Set.objects.get_or_create(
            id=435, defaults={'name': 'Age of Ascension'})
        Set.objects.get_or_create(id=452, defaults={'name': 'Worlds Collide'})
        Set.objects.get_or_create(id=479, defaults={'name': 'Mass Mutation'})
        Set.objects.get_or_create(id=496, defaults={'name': 'Dark Tidings'})
        Set.objects.get_or_create(
            id=600, defaults={'name': 'Winds of Exchange'})
        Set.objects.get_or_create(id=601, defaults={'name': 'Unchained 2022'})
        Set.objects.get_or_create(
            id=609, defaults={'name': 'Vault Masters 2023'})
        Set.objects.get_or_create(id=700, defaults={'name': 'Grim Reminders'})
        Set.objects.get_or_create(id=722, defaults={'name': 'Menagerie'})
        Set.objects.get_or_create(
            id=737, defaults={'name': 'Vault Masters 2024'})
        Set.objects.get_or_create(id=800, defaults={'name': 'Æmber Skies'})
        Set.objects.get_or_create(
            id=855, defaults={'name': 'Tokens of Change'})
        Set.objects.get_or_create(id=874, defaults={'name': 'More Mutation'})
        Set.objects.get_or_create(
            id=886, defaults={'name': 'Prophetic Visions'})
        Set.objects.get_or_create(id=907, defaults={'name': 'Discovery'})
        Set.objects.get_or_create(id=918, defaults={'name': 'Crucible Clash'})

    def make_houses(self):
        House.objects.get_or_create(name='Brobnar')
        House.objects.get_or_create(name='Dis')
        House.objects.get_or_create(name='Ekwidon')
        House.objects.get_or_create(name='Geistoid')
        House.objects.get_or_create(name='Logos')
        House.objects.get_or_create(name='Mars')
        House.objects.get_or_create(name='Redemption')
        House.objects.get_or_create(name='Sanctum')
        House.objects.get_or_create(name='Saurian')
        House.objects.get_or_create(name='Shadows')
        House.objects.get_or_create(name='Skyborn')
        House.objects.get_or_create(name='Star Alliance')
        House.objects.get_or_create(name='Unfathomable')
        House.objects.get_or_create(name='Untamed')

    def make_playgroups(self):
        pass

    def make_levels(self):
        break_vals = [0, 50, 100, 150, 200, 260, 330, 410, 500, 600, 700, 800, 900, 1000, 1100, 1200,
                      1300, 1400, 1500, 1700, 1900, 2100, 2300, 2500, 2700, 2900, 3100, 3300, 3500,
                      3700, 3900, 4100, 4300, 4500, 4700, 4900, 5100, 5300, 5500, 5900, 6300, 6700,
                      7100, 7500, 7900, 8300, 8700, 9100, 9500, 10000, 10500, 11000, 11500, 12000,
                      12500, 13000, 13500, 14000, 14500, 15000, 15500, 16000, 16500, 17000, 17500,
                      18000, 18500, 19000, 19500, 20000, 20500, 21000, 21500, 22000, 22500, 23000,
                      23500, 24000, 24500, 25000, 25500, 26000, 26500, 27000, 27500, 28000, 28500,
                      29000, 29500, 30000, 30500, 31000, 31500, 32000, 32500, 33000, 33500, 34000,
                      34500, 35000]
        for level, xp in enumerate(break_vals, start=1):
            LevelBreakpoint.objects.get_or_create(level=level,
                                                  defaults={'required_xp': xp})

    def make_leaderboards(self):
        month_leaderboard, _ = Leaderboard.objects.get_or_create(
            name='Month',
            period_frequency=LeaderboardSeasonPeriod.FrequencyOptions.MONTH,
            defaults={'sort_order': 1}
        )
        month_leaderboard.get_period_for_date(date.today())

        season_leaderboard, _ = Leaderboard.objects.get_or_create(
            name='Season',
            period_frequency=LeaderboardSeasonPeriod.FrequencyOptions.SEASON,
            defaults={'sort_order': 10}
        )
        season_leaderboard.get_period_for_date(date.today())

        Leaderboard.objects.get_or_create(
            name='All Time',
            period_frequency=LeaderboardSeasonPeriod.FrequencyOptions.ALL_TIME,
            defaults={'sort_order': 100}
        )

        all_time_season, _ = LeaderboardSeason.objects.get_or_create(
            name='All Time'
        )

        LeaderboardSeasonPeriod.objects.get_or_create(
            name='All Time',
            season=all_time_season,
            frequency=LeaderboardSeasonPeriod.FrequencyOptions.ALL_TIME,
            defaults={'start_date': date(2020, 1, 1)}
        )

    def make_events_formats(self):
        EventFormat.objects.get_or_create(
            name='Adaptive', defaults={'sort_order': 100})
        EventFormat.objects.get_or_create(
            name='Archon', defaults={'sort_order': 10})
        EventFormat.objects.get_or_create(
            name='Sealed', defaults={'sort_order': 1})

    def make_ranking_points_map(self):
        RankingPointsMap.objects.get_or_create(
            max_players=4, finishing_position=1, defaults={"points": 1200})
        RankingPointsMap.objects.get_or_create(
            max_players=4, finishing_position=2, defaults={"points": 750})
        RankingPointsMap.objects.get_or_create(
            max_players=4, finishing_position=3, defaults={"points": 469})
        RankingPointsMap.objects.get_or_create(
            max_players=8, finishing_position=1, defaults={"points": 1560})
        RankingPointsMap.objects.get_or_create(
            max_players=8, finishing_position=2, defaults={"points": 975})
        RankingPointsMap.objects.get_or_create(
            max_players=8, finishing_position=3, defaults={"points": 609})
        RankingPointsMap.objects.get_or_create(
            max_players=8, finishing_position=5, defaults={"points": 381})
        RankingPointsMap.objects.get_or_create(
            max_players=16, finishing_position=1, defaults={"points": 1950})
        RankingPointsMap.objects.get_or_create(
            max_players=16, finishing_position=2, defaults={"points": 1248})
        RankingPointsMap.objects.get_or_create(
            max_players=16, finishing_position=3, defaults={"points": 799})
        RankingPointsMap.objects.get_or_create(
            max_players=16, finishing_position=5, defaults={"points": 511})
        RankingPointsMap.objects.get_or_create(
            max_players=16, finishing_position=96, defaults={"points": 327})
        RankingPointsMap.objects.get_or_create(
            max_players=32, finishing_position=1, defaults={"points": 2340})
        RankingPointsMap.objects.get_or_create(
            max_players=32, finishing_position=2, defaults={"points": 1544})
        RankingPointsMap.objects.get_or_create(
            max_players=32, finishing_position=3, defaults={"points": 1019})
        RankingPointsMap.objects.get_or_create(
            max_players=32, finishing_position=5, defaults={"points": 673})
        RankingPointsMap.objects.get_or_create(
            max_players=32, finishing_position=9, defaults={"points": 444})
        RankingPointsMap.objects.get_or_create(
            max_players=32, finishing_position=17, defaults={"points": 293})
        RankingPointsMap.objects.get_or_create(
            max_players=64, finishing_position=1, defaults={"points": 2730})
        RankingPointsMap.objects.get_or_create(
            max_players=64, finishing_position=2, defaults={"points": 1856})
        RankingPointsMap.objects.get_or_create(
            max_players=64, finishing_position=3, defaults={"points": 1262})
        RankingPointsMap.objects.get_or_create(
            max_players=64, finishing_position=5, defaults={"points": 858})
        RankingPointsMap.objects.get_or_create(
            max_players=64, finishing_position=9, defaults={"points": 583})
        RankingPointsMap.objects.get_or_create(
            max_players=64, finishing_position=17, defaults={"points": 396})
        RankingPointsMap.objects.get_or_create(
            max_players=64, finishing_position=33, defaults={"points": 269})

    def make_avatars(self):
        cat_kc, _ = AvatarCategory.objects.get_or_create(
            name='KeyChain', defaults={'sort_order': 1})
        cat_house, _ = AvatarCategory.objects.get_or_create(
            name='Houses', defaults={'sort_order': 2})
        cat_set, _ = AvatarCategory.objects.get_or_create(
            name='Sets', defaults={'sort_order': 3})
        cat_icon, _ = AvatarCategory.objects.get_or_create(
            name='Icons', defaults={'sort_order': 4})
        cat_counter, _ = AvatarCategory.objects.get_or_create(
            name='Counters', defaults={'sort_order': 5})
        cat_misc, _ = AvatarCategory.objects.get_or_create(
            name='Other', defaults={'sort_order': 6})

        Avatar.objects.get_or_create(pmc_id='001', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/001_KeyChain_Dark.png',
                                     'category': cat_kc, 'name': 'KeyChain (Dark)', 'banner_bg_color': '131313', 'banner_stroke_color': 'ffb400', 'required_level': 0})
        Avatar.objects.get_or_create(pmc_id='002', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/002_KeyChain_Light.png',
                                     'category': cat_kc, 'name': 'KeyChain (Light)', 'banner_bg_color': 'eeeeee', 'banner_stroke_color': '69140e', 'required_level': 0})
        Avatar.objects.get_or_create(pmc_id='003', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/003_Brobnar.png',
                                     'category': cat_house, 'name': 'Brobnar', 'banner_bg_color': 'f7982e', 'banner_stroke_color': 'fdc010', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='004', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/004_Dis.png',
                                     'category': cat_house, 'name': 'Dis', 'banner_bg_color': '51494e', 'banner_stroke_color': 'e01c74', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='005', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/005_Logos.png',
                                     'category': cat_house, 'name': 'Logos', 'banner_bg_color': 'e6dfcf', 'banner_stroke_color': '00a8d8', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='006', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/006_Mars.png',
                                     'category': cat_house, 'name': 'Mars', 'banner_bg_color': '341b55', 'banner_stroke_color': '68bd45', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='007', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/007_Sanctum.png',
                                     'category': cat_house, 'name': 'Sanctum', 'banner_bg_color': '304ea2', 'banner_stroke_color': 'f9ee44', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='008', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/008_Shadows.png',
                                     'category': cat_house, 'name': 'Shadows', 'banner_bg_color': 'd5cbc5', 'banner_stroke_color': '1b172c', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='009', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/009_Untamed.png',
                                     'category': cat_house, 'name': 'Untamed', 'banner_bg_color': '004123', 'banner_stroke_color': 'e26a28', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='010', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/010_Saurian.png',
                                     'category': cat_house, 'name': 'Saurian', 'banner_bg_color': 'fff8e6', 'banner_stroke_color': '47bccd', 'required_level': 4})
        Avatar.objects.get_or_create(pmc_id='011', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/011_Star_Alliance.png',
                                     'category': cat_house, 'name': 'Star Alliance', 'banner_bg_color': 'f8bf7f', 'banner_stroke_color': 'd71c23', 'required_level': 4})
        Avatar.objects.get_or_create(pmc_id='012', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/012_Unfathomable.png',
                                     'category': cat_house, 'name': 'Unfathomable', 'banner_bg_color': '292d56', 'banner_stroke_color': '13becf', 'required_level': 4})
        Avatar.objects.get_or_create(pmc_id='013', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/013_Ekwidon.png',
                                     'category': cat_house, 'name': 'Ekwidon', 'banner_bg_color': '92d3c9', 'banner_stroke_color': 'e3ba4e', 'required_level': 5})
        Avatar.objects.get_or_create(pmc_id='014', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/014_Geistoid.png',
                                     'category': cat_house, 'name': 'Geistoid', 'banner_bg_color': '723f98', 'banner_stroke_color': 'fff200', 'required_level': 5})
        Avatar.objects.get_or_create(pmc_id='015', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/015_Skyborn.png',
                                     'category': cat_house, 'name': 'Skyborn', 'banner_bg_color': '0f5d96', 'banner_stroke_color': 'f9a146', 'required_level': 5})
        Avatar.objects.get_or_create(pmc_id='016', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/016_Redemption.png',
                                     'category': cat_house, 'name': 'Redemption', 'banner_bg_color': 'f6ecc2', 'banner_stroke_color': 'f06e75', 'required_level': 5})
        Avatar.objects.get_or_create(pmc_id='017', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/017_CotA.png', 'category': cat_set,
                                     'name': 'Call of the Archons', 'banner_bg_color': '4f1212', 'banner_stroke_color': 'f89a3a', 'required_level': 7})
        Avatar.objects.get_or_create(pmc_id='018', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/018_AoA.png', 'category': cat_set,
                                     'name': 'Age of Ascension', 'banner_bg_color': '173045', 'banner_stroke_color': 'fff972', 'required_level': 7})
        Avatar.objects.get_or_create(pmc_id='019', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/019_WC.png', 'category': cat_set,
                                     'name': 'Worlds Collide', 'banner_bg_color': '291030', 'banner_stroke_color': 'f5e073', 'required_level': 7})
        Avatar.objects.get_or_create(pmc_id='020', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/020_MM.png',
                                     'category': cat_set, 'name': 'Mass Mutation', 'banner_bg_color': '1a1a1a', 'banner_stroke_color': 'ffff50', 'required_level': 7})
        Avatar.objects.get_or_create(pmc_id='021', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/021_DT.png',
                                     'category': cat_set, 'name': 'Dark Tidings', 'banner_bg_color': '272b4f', 'banner_stroke_color': '18bbed', 'required_level': 7})
        Avatar.objects.get_or_create(pmc_id='022', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/022_WoE.png', 'category': cat_set,
                                     'name': 'Winds of Exchange', 'banner_bg_color': '444a3b', 'banner_stroke_color': 'd09434', 'required_level': 8})
        Avatar.objects.get_or_create(pmc_id='023', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/023_GR.png', 'category': cat_set,
                                     'name': 'Grim Reminders', 'banner_bg_color': '003f8c', 'banner_stroke_color': 'ea4025', 'required_level': 8})
        Avatar.objects.get_or_create(pmc_id='024', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/024_AS.png',
                                     'category': cat_set, 'name': 'Æmber Skies', 'banner_bg_color': 'ffbc79', 'banner_stroke_color': '693400', 'required_level': 8})
        Avatar.objects.get_or_create(pmc_id='025', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/025_PV.png', 'category': cat_set,
                                     'name': 'Prophetic Visions', 'banner_bg_color': '26121e', 'banner_stroke_color': 'f0eacc', 'required_level': 8})
        Avatar.objects.get_or_create(pmc_id='026', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/026_MORE.png',
                                     'category': cat_set, 'name': 'More Mutation', 'banner_bg_color': '1a1a1a', 'banner_stroke_color': 'aa1e23', 'required_level': 8})
        Avatar.objects.get_or_create(pmc_id='027', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/027_ToC.png', 'category': cat_set,
                                     'name': 'Tokens of Change', 'banner_bg_color': 'ba181b', 'banner_stroke_color': 'f6ecc2', 'required_level': 8})
        Avatar.objects.get_or_create(pmc_id='028', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/028_DISC.png',
                                     'category': cat_set, 'name': 'Discovery', 'banner_bg_color': '213c4a', 'banner_stroke_color': 'ffffff', 'required_level': 0})
        Avatar.objects.get_or_create(pmc_id='030', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/030_UC23.png',
                                     'category': cat_set, 'name': 'Unchained', 'banner_bg_color': 'ffffff', 'banner_stroke_color': '000000', 'required_level': 9})
        Avatar.objects.get_or_create(pmc_id='031', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/031_MN24.png',
                                     'category': cat_set, 'name': 'Menagerie', 'banner_bg_color': 'a5a19b', 'banner_stroke_color': 'eadc83', 'required_level': 9})
        Avatar.objects.get_or_create(pmc_id='032', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/032_VM23.png', 'category': cat_set,
                                     'name': 'Vault Masters 2023', 'banner_bg_color': '0f284b', 'banner_stroke_color': 'ffffff', 'required_level': 9})
        Avatar.objects.get_or_create(pmc_id='033', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/033_VM24.png', 'category': cat_set,
                                     'name': 'Vault Masters 2024', 'banner_bg_color': '526473', 'banner_stroke_color': 'fcee21', 'required_level': 9})
        Avatar.objects.get_or_create(pmc_id='035', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/035_Stun.png',
                                     'category': cat_counter, 'name': 'Stun', 'banner_bg_color': 'fff19a', 'banner_stroke_color': '000000', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='036', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/036_Ward.png',
                                     'category': cat_counter, 'name': 'Ward', 'banner_bg_color': '2a4ca0', 'banner_stroke_color': '000000', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='037', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/037_Enrage.png',
                                     'category': cat_counter, 'name': 'Enrage', 'banner_bg_color': 'f9bf75', 'banner_stroke_color': '000000', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='038', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/038_PowerCounter.png',
                                     'category': cat_counter, 'name': 'Power Counter', 'banner_bg_color': 'eaebed', 'banner_stroke_color': 'c72329', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='039', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/039_Chain.png',
                                     'category': cat_counter, 'name': 'Chain', 'banner_bg_color': 'c7c5be', 'banner_stroke_color': '233e96', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='040', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/040_Aember.png',
                                     'category': cat_counter, 'name': 'Æmber', 'banner_bg_color': 'fcb934', 'banner_stroke_color': 'fddb29', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='041', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/041_YellowKey.png',
                                     'category': cat_counter, 'name': 'Yellow Key', 'banner_bg_color': 'fff1a4', 'banner_stroke_color': 'f5dc5f', 'required_level': 6})
        Avatar.objects.get_or_create(pmc_id='042', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/042_BlueKey.png',
                                     'category': cat_counter, 'name': 'Blue Key', 'banner_bg_color': '064ea1', 'banner_stroke_color': '2bc0f2', 'required_level': 12})
        Avatar.objects.get_or_create(pmc_id='043', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/043_RedKey.png',
                                     'category': cat_counter, 'name': 'Red Key', 'banner_bg_color': '79131d', 'banner_stroke_color': 'd73221', 'required_level': 18})
        Avatar.objects.get_or_create(pmc_id='044', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/044_AemberBonus.png',
                                     'category': cat_icon, 'name': 'Æmber Icon', 'banner_bg_color': 'f8a821', 'banner_stroke_color': '231f20', 'required_level': 15})
        Avatar.objects.get_or_create(pmc_id='045', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/045_CaptureBonus.png',
                                     'category': cat_icon, 'name': 'Capture Icon', 'banner_bg_color': '939598', 'banner_stroke_color': '231f20', 'required_level': 15})
        Avatar.objects.get_or_create(pmc_id='046', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/046_DamageBonus.png',
                                     'category': cat_icon, 'name': 'Damage Icon', 'banner_bg_color': 'e63e25', 'banner_stroke_color': '231f20', 'required_level': 15})
        Avatar.objects.get_or_create(pmc_id='047', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/047_DrawBonus.png',
                                     'category': cat_icon, 'name': 'Draw Icon', 'banner_bg_color': '66c9f2', 'banner_stroke_color': '231f20', 'required_level': 15})
        Avatar.objects.get_or_create(pmc_id='048', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/048_DiscardBonus.png',
                                     'category': cat_icon, 'name': 'Discard Icon', 'banner_bg_color': '92278f', 'banner_stroke_color': '231f20', 'required_level': 15})
        Avatar.objects.get_or_create(pmc_id='049', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/049_VaultTour.png',
                                     'category': cat_misc, 'name': 'Vault Tour', 'banner_bg_color': 'ffc364', 'banner_stroke_color': '636059', 'required_level': 19})
        Avatar.objects.get_or_create(pmc_id='050', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/050_Action.png',
                                     'category': cat_misc, 'name': 'Neon Action', 'banner_bg_color': '121212', 'banner_stroke_color': '04d9ff', 'required_level': 20})
        Avatar.objects.get_or_create(pmc_id='051', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/051_Artifact.png',
                                     'category': cat_misc, 'name': 'Neon Artifact', 'banner_bg_color': '121212', 'banner_stroke_color': '39ff14', 'required_level': 20})
        Avatar.objects.get_or_create(pmc_id='052', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/052_Creature.png',
                                     'category': cat_misc, 'name': 'Neon Creature', 'banner_bg_color': '121212', 'banner_stroke_color': 'ff13f0', 'required_level': 20})
        Avatar.objects.get_or_create(pmc_id='053', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/053_Upgrade.png',
                                     'category': cat_misc, 'name': 'Neon Upgrade', 'banner_bg_color': '121212', 'banner_stroke_color': 'FFFF00', 'required_level': 20})
        Avatar.objects.get_or_create(pmc_id='054', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/054_Keyraken.png',
                                     'category': cat_house, 'name': 'Keyraken', 'banner_bg_color': '601a2d', 'banner_stroke_color': 'ffe100', 'required_level': 17})
        Avatar.objects.get_or_create(pmc_id='055', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/055_MCW.png', 'category': cat_set,
                                     'name': 'Martian Civil War', 'banner_bg_color': '341b55', 'banner_stroke_color': 'eb1f4f', 'required_level': 9})
        Avatar.objects.get_or_create(pmc_id='056', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/056_KeyChain_Bronze.png',
                                     'category': cat_kc, 'name': 'KeyChain (Bronze)', 'banner_bg_color': '6e3d34', 'banner_stroke_color': 'dd9b72', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='057', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/057_KeyChain_Silver.png',
                                     'category': cat_kc, 'name': 'KeyChain (Silver)', 'banner_bg_color': 'ebebeb', 'banner_stroke_color': '979797', 'required_level': 20})
        Avatar.objects.get_or_create(pmc_id='058', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/058_KeyChain_Gold.png',
                                     'category': cat_kc, 'name': 'KeyChain (Gold)', 'banner_bg_color': 'ffee90', 'banner_stroke_color': 'edc967', 'required_level': 40})
        Avatar.objects.get_or_create(pmc_id='059', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/059_KeyChain_Ascension.png',
                                     'category': cat_kc, 'name': 'KeyChain (Ascension)', 'banner_bg_color': '151515', 'banner_stroke_color': 'ffea00', 'required_level': 50})
        Avatar.objects.get_or_create(pmc_id='060', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/060_ChromaKeys.png',
                                     'category': cat_counter, 'name': 'Chroma Keys', 'banner_bg_color': 'e9e9e9', 'banner_stroke_color': 'ffffff', 'required_level': 18})

    def make_backgrounds(self):
        cat_kc, _ = BackgroundCategory.objects.get_or_create(
            name='KeyChain', defaults={'sort_order': 1})
        cat_misc, _ = BackgroundCategory.objects.get_or_create(
            name='Other', defaults={'sort_order': 6})

        Background.objects.get_or_create(pmc_id='001', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/001_KeyChain_Dark.png',
                                         'name': 'KeyChain (Dark)', 'category': cat_kc, 'required_level': 0, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='002', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/002_KeyChain_Light.png',
                                         'name': 'KeyChain (Light)', 'category': cat_kc, 'required_level': 0, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='003', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/003_Discovery.png',
                                         'name': 'Discovery', 'category': cat_kc, 'required_level': 0, 'artist_credit': 'David Otálora'})
        Background.objects.get_or_create(pmc_id='004', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/004_SloppyLabwork.png',
                                         'name': 'Sloppy Labwork', 'category': cat_kc, 'required_level': 3, 'artist_credit': 'Hans Krill'})
        Background.objects.get_or_create(pmc_id='005', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/005_EnsignClark.png',
                                         'name': 'Ensign Clark', 'category': cat_kc, 'required_level': 13, 'artist_credit': 'Xavi Planas'})
        Background.objects.get_or_create(pmc_id='006', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/006_PaleogeneSociety.png',
                                         'name': 'Paleogene Society', 'category': cat_kc, 'required_level': 13, 'artist_credit': 'VictorG.Art'})
        Background.objects.get_or_create(pmc_id='008', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/008_HumbleRestraint.png',
                                         'name': 'Humble Restraint', 'category': cat_kc, 'required_level': 12, 'artist_credit': 'Nicholas Hoe'})
        Background.objects.get_or_create(pmc_id='010', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/010_TheRedCotAComin.png',
                                         'name': 'The Red CotA Comin\'', 'category': cat_kc, 'required_level': 7, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='011', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/011_SingingTheBlues.png',
                                         'name': 'Sing the Blues oA', 'category': cat_kc, 'required_level': 7, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='012', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/012_TheAemberSky.png',
                                         'name': 'The Æmber Sky', 'category': cat_kc, 'required_level': 8, 'artist_credit': 'Scott Schomburg'})
        Background.objects.get_or_create(pmc_id='013', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/013_GrimReminders.png',
                                         'name': 'Grim Reminders', 'category': cat_kc, 'required_level': 8, 'artist_credit': 'Kevin Sidharta'})
        Background.objects.get_or_create(pmc_id='014', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/014_EdgeOfTheWorld.png',
                                         'name': 'Edge of the World', 'category': cat_kc, 'required_level': 14, 'artist_credit': 'Julia Alentseva'})
        Background.objects.get_or_create(pmc_id='015', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/015_BadPenny.png',
                                         'name': 'Bad Penny', 'category': cat_kc, 'required_level': 3, 'artist_credit': 'Nasrul Hakim'})
        Background.objects.get_or_create(pmc_id='016', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/016_Chaostadon.png',
                                         'name': 'Chaostadon', 'category': cat_kc, 'required_level': 4, 'artist_credit': 'Kevin Sidharta'})
        Background.objects.get_or_create(pmc_id='017', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/017_TheOldBook.png',
                                         'name': 'The Old Book', 'category': cat_kc, 'required_level': 2, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='018', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/018_ID.png',
                                         'name': 'ID Check', 'category': cat_kc, 'required_level': 21, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='019', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/019_TheKeyraken.png',
                                         'name': 'The Keyraken', 'category': cat_kc, 'required_level': 17, 'artist_credit': 'Kevin Sidharta'})
        Background.objects.get_or_create(pmc_id='020', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/020_KeymanderSpectralInvestigator.png',
                                         'name': 'Keymander: Spectral Investigator', 'category': cat_kc, 'required_level': 16, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='021', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/021_KeymanderPrimordialSerpent.png',
                                         'name': 'Keymander: Primordial Serpent', 'category': cat_kc, 'required_level': 16, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='022', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/022_KeymanderWeirdo.png',
                                         'name': 'Keymander: Weirdo', 'category': cat_kc, 'required_level': 16, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='023', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/023_MightMakesRight.png',
                                         'name': 'Might Makes Right', 'category': cat_kc, 'required_level': 3, 'artist_credit': 'Monztre'})
        Background.objects.get_or_create(pmc_id='024', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/024_HauntedHouse.png',
                                         'name': 'Haunted House', 'category': cat_kc, 'required_level': 5, 'artist_credit': 'BalanceSheet'})
        Background.objects.get_or_create(pmc_id='025', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/025_BrendTheFanatic.png',
                                         'name': 'Brend the Fanatic', 'category': cat_kc, 'required_level': 12, 'artist_credit': 'Djib'})
        Background.objects.get_or_create(pmc_id='026', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/026_AbyssalConspiracy.png',
                                         'name': 'The Abyssal Conspiracy', 'category': cat_kc, 'required_level': 17, 'artist_credit': 'Kevin Sidharta'})
        Background.objects.get_or_create(pmc_id='027', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/027_GettingStarted.png',
                                         'name': 'Welcome to the Jungle', 'category': cat_kc, 'required_level': 2, 'artist_credit': 'David Kegg'})
        Background.objects.get_or_create(pmc_id='028', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/028_AmmoniaClouds.png',
                                         'name': 'Ammonia Clouds', 'category': cat_kc, 'required_level': 3, 'artist_credit': 'BalanceSheet'})
        Background.objects.get_or_create(pmc_id='029', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/029_CatenaFiend.png',
                                         'name': 'Catena Fiend', 'category': cat_kc, 'required_level': 22, 'artist_credit': 'Arthur Magalhaes'})
        Background.objects.get_or_create(pmc_id='030', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/030_KelifiDragon.png',
                                         'name': 'Kalifi Dragon', 'category': cat_kc, 'required_level': 11, 'artist_credit': 'Caio Monteiro'})
        Background.objects.get_or_create(pmc_id='031', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/031_DominatorBauble.png',
                                         'name': 'Dominator Bauble', 'category': cat_kc, 'required_level': 11, 'artist_credit': 'Caravan Studio'})
        Background.objects.get_or_create(pmc_id='032', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/032_CloudburstCommand.png',
                                         'name': 'Cloudburst Command', 'category': cat_kc, 'required_level': 5, 'artist_credit': 'David Otálora'})
        Background.objects.get_or_create(pmc_id='033', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/033_PunctuatedEquilibrium.png',
                                         'name': 'Punctuated Equilibrium', 'category': cat_kc, 'required_level': 13, 'artist_credit': 'Jessé Suursoo'})
        Background.objects.get_or_create(pmc_id='034', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/034_FuzzyGruen.png',
                                         'name': 'Fuzzy Gruen', 'category': cat_kc, 'required_level': 3, 'artist_credit': 'Adam Vehige'})
        Background.objects.get_or_create(pmc_id='035', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/035_DarkTidings.png',
                                         'name': 'Dark Tidings', 'category': cat_kc, 'required_level': 8, 'artist_credit': 'Ângelo Bortolini'})
        Background.objects.get_or_create(pmc_id='036', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/036_Kaupe.png',
                                         'name': 'Kaupe', 'category': cat_kc, 'required_level': 4, 'artist_credit': 'Art Tavern'})
        Background.objects.get_or_create(pmc_id='037', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/037_Almsmaster.png',
                                         'name': 'Almsmaster', 'category': cat_kc, 'required_level': 3, 'artist_credit': 'Ivan Tao'})
        Background.objects.get_or_create(pmc_id='038', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/038_LibraryOfBabble.png',
                                         'name': 'Library of Babble', 'category': cat_kc, 'required_level': 11, 'artist_credit': 'BalanceSheet'})
        Background.objects.get_or_create(pmc_id='039', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/039_Memolith.png',
                                         'name': 'Memolith', 'category': cat_kc, 'required_level': 10, 'artist_credit': 'Francisco Badilla'})
        Background.objects.get_or_create(pmc_id='040', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/040_DrXyloxxzlphrex.png',
                                         'name': 'Dr. Xyloxxzlphrex', 'category': cat_kc, 'required_level': 12, 'artist_credit': 'Djib'})
        Background.objects.get_or_create(pmc_id='041', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/041_UnlockedGateway.png',
                                         'name': 'Unlocked Gateway', 'category': cat_kc, 'required_level': 3, 'artist_credit': 'Sean Donaldson'})
        Background.objects.get_or_create(pmc_id='042', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/042_VaultAssault.png',
                                         'name': 'Vault Assault', 'category': cat_kc, 'required_level': 6, 'artist_credit': 'Shady Curi'})
        Background.objects.get_or_create(pmc_id='043', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/043_NicheMarket.png',
                                         'name': 'Niche Market', 'category': cat_kc, 'required_level': 14, 'artist_credit': 'Jeferson Cordeiro'})
        Background.objects.get_or_create(pmc_id='044', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/044_MoonLightSpecial.png',
                                         'name': 'Moon Light Special', 'category': cat_kc, 'required_level': 5, 'artist_credit': 'Kaion Luong'})
        Background.objects.get_or_create(pmc_id='045', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/045_EctoCharge.png',
                                         'name': 'Ecto-Charge', 'category': cat_kc, 'required_level': 14, 'artist_credit': 'BalanceSheet'})
        Background.objects.get_or_create(pmc_id='046', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/046_TacticalOfficerMoon.png',
                                         'name': 'Tactical Officer Moon', 'category': cat_kc, 'required_level': 4, 'artist_credit': 'Colin Searle'})
        Background.objects.get_or_create(pmc_id='047', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/047_TheChosenOne.png',
                                         'name': 'The Chosen One', 'category': cat_kc, 'required_level': 14, 'artist_credit': 'Mariana Ennes'})
        Background.objects.get_or_create(pmc_id='048', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/048_BurnTheStockpile.png',
                                         'name': 'Burn the Stockpile', 'category': cat_kc, 'required_level': 22, 'artist_credit': 'BalanceSheet'})
        Background.objects.get_or_create(pmc_id='049', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/049_NeonBlue.png',
                                         'name': 'Neon Blue', 'category': cat_kc, 'required_level': 20, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='050', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/050_NeonGreen.png',
                                         'name': 'Neon Green', 'category': cat_kc, 'required_level': 20, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='051', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/051_NeonPink.png',
                                         'name': 'Neon Pink', 'category': cat_kc, 'required_level': 20, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='052', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/052_NeonYellow.png',
                                         'name': 'Neon Yellow', 'category': cat_kc, 'required_level': 20, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='053', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/053_KeyChain_Bronze.png',
                                         'name': 'KeyChain (Bronze)', 'category': cat_kc, 'required_level': 10, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='054', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/054_KeyChain_Silver.png',
                                         'name': 'KeyChain (Silver)', 'category': cat_kc, 'required_level': 20, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='055', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/055_KeyChain_Gold.png',
                                         'name': 'KeyChain (Gold)', 'category': cat_kc, 'required_level': 40, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='056', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/056_KeyChain_Ascension.png',
                                         'name': 'KeyChain (Ascension)', 'category': cat_kc, 'required_level': 50, 'artist_credit': None})
        Background.objects.get_or_create(pmc_id='057', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/057_VindicationOutpost.png',
                                         'name': 'Vindication Outpost', 'category': cat_kc, 'required_level': 13, 'artist_credit': 'Michael Angelo Dulay'})
        Background.objects.get_or_create(pmc_id='058', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/058_RedeemerAmara.png',
                                         'name': 'Redeemer Amara', 'category': cat_misc, 'required_level': 5, 'artist_credit': 'Allison Capa'})

    def make_playgroup_types(self):
        PlaygroupType.objects.get_or_create(name='Game Store')
