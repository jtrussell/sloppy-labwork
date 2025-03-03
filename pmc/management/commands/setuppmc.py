from django.core.management.base import BaseCommand
from pmc.models import LevelBreakpoint, EventFormat, Leaderboard, LeaderboardSeason, LeaderboardSeasonPeriod, Avatar, Background
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

        self.stdout.write('Making avatars... ', ending='')
        self.make_avatars()
        self.stdout.write(self.style.SUCCESS('OK'))

        self.stdout.write('Making backgrounds... ', ending='')
        self.make_backgrounds()
        self.stdout.write(self.style.SUCCESS('OK'))

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
        pass

    def make_avatars(self):
        Avatar.objects.get_or_create(pmc_id='001', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/001_KeyChain_Dark.png',
                                     'category_label': 'KeyChain', 'name': 'KeyChain (Dark)', 'banner_bg_color': '131313', 'banner_stroke_color': 'ffb400', 'required_level': 0})
        Avatar.objects.get_or_create(pmc_id='002', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/002_KeyChain_Light.png',
                                     'category_label': 'KeyChain', 'name': 'KeyChain (Light)', 'banner_bg_color': 'eeeeee', 'banner_stroke_color': '69140e', 'required_level': 0})
        Avatar.objects.get_or_create(pmc_id='003', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/003_Brobnar.png',
                                     'category_label': 'Houses', 'name': 'Brobnar', 'banner_bg_color': 'f7982e', 'banner_stroke_color': '00a8d8', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='004', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/004_Dis.png',
                                     'category_label': 'Houses', 'name': 'Dis', 'banner_bg_color': '51494e', 'banner_stroke_color': 'e01c74', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='005', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/005_Logos.png',
                                     'category_label': 'Houses', 'name': 'Logos', 'banner_bg_color': 'e6dfcf', 'banner_stroke_color': '00a8d8', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='006', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/006_Mars.png',
                                     'category_label': 'Houses', 'name': 'Mars', 'banner_bg_color': '341b55', 'banner_stroke_color': '68bd45', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='007', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/007_Sanctum.png',
                                     'category_label': 'Houses', 'name': 'Sanctum', 'banner_bg_color': '304ea2', 'banner_stroke_color': 'f9ee44', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='008', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/008_Shadows.png',
                                     'category_label': 'Houses', 'name': 'Shadows', 'banner_bg_color': 'd5cbc5', 'banner_stroke_color': '1b172c', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='009', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/009_Untamed.png',
                                     'category_label': 'Houses', 'name': 'Untamed', 'banner_bg_color': '004123', 'banner_stroke_color': 'e26a28', 'required_level': 2})
        Avatar.objects.get_or_create(pmc_id='010', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/010_Saurian.png',
                                     'category_label': 'Houses', 'name': 'Saurian', 'banner_bg_color': 'fff8e6', 'banner_stroke_color': '47bccd', 'required_level': 4})
        Avatar.objects.get_or_create(pmc_id='011', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/011_Star_Alliance.png',
                                     'category_label': 'Houses', 'name': 'Star Alliance', 'banner_bg_color': 'f8bf7f', 'banner_stroke_color': 'd71c23', 'required_level': 4})
        Avatar.objects.get_or_create(pmc_id='012', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/012_Unfathomable.png',
                                     'category_label': 'Houses', 'name': 'Unfathomable', 'banner_bg_color': '292d56', 'banner_stroke_color': '13becf', 'required_level': 4})
        Avatar.objects.get_or_create(pmc_id='013', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/013_Ekwidon.png',
                                     'category_label': 'Houses', 'name': 'Ekwidon', 'banner_bg_color': '92d3c9', 'banner_stroke_color': 'e3ba4e', 'required_level': 5})
        Avatar.objects.get_or_create(pmc_id='014', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/014_Geistoid.png',
                                     'category_label': 'Houses', 'name': 'Geistoid', 'banner_bg_color': '723f98', 'banner_stroke_color': 'fff200', 'required_level': 5})
        Avatar.objects.get_or_create(pmc_id='015', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/015_Skyborn.png',
                                     'category_label': 'Houses', 'name': 'Skyborn', 'banner_bg_color': '0f5d96', 'banner_stroke_color': 'f9a146', 'required_level': 5})
        Avatar.objects.get_or_create(pmc_id='016', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/016_Redemption.png',
                                     'category_label': 'Houses', 'name': 'Redemption', 'banner_bg_color': 'f6ecc2', 'banner_stroke_color': 'f06e75', 'required_level': 5})
        Avatar.objects.get_or_create(pmc_id='017', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/017_CotA.png', 'category_label': 'Sets',
                                     'name': 'Call of the Archons', 'banner_bg_color': '4f1212', 'banner_stroke_color': 'f89a3a', 'required_level': 7})
        Avatar.objects.get_or_create(pmc_id='018', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/018_AoA.png', 'category_label': 'Sets',
                                     'name': 'Age of Ascension', 'banner_bg_color': '173045', 'banner_stroke_color': 'fff972', 'required_level': 7})
        Avatar.objects.get_or_create(pmc_id='019', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/019_WC.png', 'category_label': 'Sets',
                                     'name': 'Worlds Collide', 'banner_bg_color': '291030', 'banner_stroke_color': 'f5e073', 'required_level': 7})
        Avatar.objects.get_or_create(pmc_id='020', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/020_MM.png',
                                     'category_label': 'Sets', 'name': 'Mass Mutation', 'banner_bg_color': '1a1a1a', 'banner_stroke_color': 'ffff50', 'required_level': 7})
        Avatar.objects.get_or_create(pmc_id='021', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/021_DT.png',
                                     'category_label': 'Sets', 'name': 'Dark Tidings', 'banner_bg_color': '272b4f', 'banner_stroke_color': '18bbed', 'required_level': 7})
        Avatar.objects.get_or_create(pmc_id='022', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/022_WoE.png', 'category_label': 'Sets',
                                     'name': 'Winds of Exchange', 'banner_bg_color': '444a3b', 'banner_stroke_color': 'd09434', 'required_level': 8})
        Avatar.objects.get_or_create(pmc_id='023', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/023_GR.png', 'category_label': 'Sets',
                                     'name': 'Grim Reminders', 'banner_bg_color': '003f8c', 'banner_stroke_color': 'ea4025', 'required_level': 8})
        Avatar.objects.get_or_create(pmc_id='024', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/024_AS.png',
                                     'category_label': 'Sets', 'name': 'Æmber Skies', 'banner_bg_color': 'ffbc79', 'banner_stroke_color': '693400', 'required_level': 8})
        Avatar.objects.get_or_create(pmc_id='025', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/025_PV.png', 'category_label': 'Sets',
                                     'name': 'Prophetic Visions', 'banner_bg_color': '26121e', 'banner_stroke_color': 'f0eacc', 'required_level': 8})
        Avatar.objects.get_or_create(pmc_id='026', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/026_MORE.png',
                                     'category_label': 'Sets', 'name': 'More Mutation', 'banner_bg_color': '1a1a1a', 'banner_stroke_color': 'aa1e23', 'required_level': 8})
        Avatar.objects.get_or_create(pmc_id='027', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/027_ToC.png', 'category_label': 'Sets',
                                     'name': 'Tokens of Change', 'banner_bg_color': 'ba181b', 'banner_stroke_color': 'f6ecc2', 'required_level': 8})
        Avatar.objects.get_or_create(pmc_id='028', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/028_DISC.png',
                                     'category_label': 'Sets', 'name': 'Discovery', 'banner_bg_color': '213c4a', 'banner_stroke_color': 'ffffff', 'required_level': 0})
        Avatar.objects.get_or_create(pmc_id='030', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/030_UC23.png',
                                     'category_label': 'Sets', 'name': 'Unchained', 'banner_bg_color': 'ffffff', 'banner_stroke_color': '000000', 'required_level': 9})
        Avatar.objects.get_or_create(pmc_id='031', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/031_MN24.png',
                                     'category_label': 'Sets', 'name': 'Menagerie', 'banner_bg_color': 'a5a19b', 'banner_stroke_color': 'eadc83', 'required_level': 9})
        Avatar.objects.get_or_create(pmc_id='032', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/032_VM23.png', 'category_label': 'Sets',
                                     'name': 'Vault Masters 2023', 'banner_bg_color': '0f284b', 'banner_stroke_color': 'ffffff', 'required_level': 9})
        Avatar.objects.get_or_create(pmc_id='033', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/033_VM24.png', 'category_label': 'Sets',
                                     'name': 'Vault Masters 2024', 'banner_bg_color': '526473', 'banner_stroke_color': 'fcee21', 'required_level': 9})
        Avatar.objects.get_or_create(pmc_id='035', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/035_Stun.png',
                                     'category_label': 'Counters', 'name': 'Stun', 'banner_bg_color': 'fff19a', 'banner_stroke_color': '000000', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='036', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/036_Ward.png',
                                     'category_label': 'Counters', 'name': 'Ward', 'banner_bg_color': '2a4ca0', 'banner_stroke_color': '000000', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='037', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/037_Enrage.png',
                                     'category_label': 'Counters', 'name': 'Enrage', 'banner_bg_color': 'f9bf75', 'banner_stroke_color': '000000', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='038', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/038_PowerCounter.png',
                                     'category_label': 'Counters', 'name': 'Power Counter', 'banner_bg_color': 'eaebed', 'banner_stroke_color': 'c72329', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='039', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/039_Chain.png',
                                     'category_label': 'Counters', 'name': 'Chain', 'banner_bg_color': 'c7c5be', 'banner_stroke_color': '233e96', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='041', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/041_YellowKey.png',
                                     'category_label': 'Counters', 'name': 'Yellow Key', 'banner_bg_color': 'fff1a4', 'banner_stroke_color': 'f5dc5f', 'required_level': 6})
        Avatar.objects.get_or_create(pmc_id='042', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/042_BlueKey.png',
                                     'category_label': 'Counters', 'name': 'Blue Key', 'banner_bg_color': '064ea1', 'banner_stroke_color': '2bc0f2', 'required_level': 12})
        Avatar.objects.get_or_create(pmc_id='043', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/043_RedKey.png',
                                     'category_label': 'Counters', 'name': 'Red Key', 'banner_bg_color': '79131d', 'banner_stroke_color': 'd73221', 'required_level': 18})
        Avatar.objects.get_or_create(pmc_id='044', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/044_AemberBonus.png',
                                     'category_label': 'Icons', 'name': 'Æmber Icon', 'banner_bg_color': 'f8a821', 'banner_stroke_color': '231f20', 'required_level': 15})
        Avatar.objects.get_or_create(pmc_id='045', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/045_CaptureBonus.png',
                                     'category_label': 'Icons', 'name': 'Capture Icon', 'banner_bg_color': '939598', 'banner_stroke_color': '231f20', 'required_level': 15})
        Avatar.objects.get_or_create(pmc_id='046', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/046_DamageBonus.png',
                                     'category_label': 'Icons', 'name': 'Damage Icon', 'banner_bg_color': 'e63e25', 'banner_stroke_color': '231f20', 'required_level': 15})
        Avatar.objects.get_or_create(pmc_id='047', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/047_DrawBonus.png',
                                     'category_label': 'Icons', 'name': 'Draw Icon', 'banner_bg_color': '66c9f2', 'banner_stroke_color': '231f20', 'required_level': 15})
        Avatar.objects.get_or_create(pmc_id='048', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/048_DiscardBonus.png',
                                     'category_label': 'Icons', 'name': 'Discard Icon', 'banner_bg_color': '92278f', 'banner_stroke_color': '231f20', 'required_level': 15})
        Avatar.objects.get_or_create(pmc_id='049', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/049_VaultTour.png',
                                     'category_label': 'Other', 'name': 'Vault Tour', 'banner_bg_color': 'ffc364', 'banner_stroke_color': '636059', 'required_level': 19})
        Avatar.objects.get_or_create(pmc_id='050', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/050_Action.png',
                                     'category_label': 'Card Types', 'name': 'Neon Action', 'banner_bg_color': '121212', 'banner_stroke_color': '04d9ff', 'required_level': 20})
        Avatar.objects.get_or_create(pmc_id='051', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/051_Artifact.png',
                                     'category_label': 'Card Types', 'name': 'Neon Artifact', 'banner_bg_color': '121212', 'banner_stroke_color': '39ff14', 'required_level': 20})
        Avatar.objects.get_or_create(pmc_id='052', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/052_Creature.png',
                                     'category_label': 'Card Types', 'name': 'Neon Creature', 'banner_bg_color': '121212', 'banner_stroke_color': 'ff13f0', 'required_level': 20})
        Avatar.objects.get_or_create(pmc_id='053', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/053_Upgrade.png',
                                     'category_label': 'Card Types', 'name': 'Neon Upgrade', 'banner_bg_color': '121212', 'banner_stroke_color': 'FFFF00', 'required_level': 20})
        Avatar.objects.get_or_create(pmc_id='054', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/054_Keyraken.png',
                                     'category_label': 'Houses', 'name': 'Keyraken', 'banner_bg_color': '601a2d', 'banner_stroke_color': 'ffe100', 'required_level': 17})
        Avatar.objects.get_or_create(pmc_id='055', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/055_MCW.png', 'category_label': 'Sets',
                                     'name': 'Martian Civil War', 'banner_bg_color': '341b55', 'banner_stroke_color': 'eb1f4f', 'required_level': 9})
        Avatar.objects.get_or_create(pmc_id='056', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/056_KeyChain_Bronze.png',
                                     'category_label': 'KeyChain', 'name': 'KeyChain (Bronze)', 'banner_bg_color': '6e3d34', 'banner_stroke_color': 'dd9b72', 'required_level': 10})
        Avatar.objects.get_or_create(pmc_id='057', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/057_KeyChain_Silver.png',
                                     'category_label': 'KeyChain', 'name': 'KeyChain (Silver)', 'banner_bg_color': 'ebebeb', 'banner_stroke_color': '979797', 'required_level': 20})
        Avatar.objects.get_or_create(pmc_id='058', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/058_KeyChain_Gold.png',
                                     'category_label': 'KeyChain', 'name': 'KeyChain (Gold)', 'banner_bg_color': 'ffee90', 'banner_stroke_color': 'edc967', 'required_level': 40})
        Avatar.objects.get_or_create(pmc_id='059', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/059_KeyChain_Ascension.png',
                                     'category_label': 'KeyChain', 'name': 'KeyChain (Ascension)', 'banner_bg_color': '151515', 'banner_stroke_color': 'ffea00', 'required_level': 50})
        Avatar.objects.get_or_create(pmc_id='060', defaults={'src': 'https://static.sloppylabwork.com/pmc/avatars/060_ChromaKeys.png',
                                     'category_label': 'Counters', 'name': 'Chroma Keys', 'banner_bg_color': 'e9e9e9', 'banner_stroke_color': 'ffffff', 'required_level': 18})

    def make_backgrounds(self):
        Background.objects.get_or_create(pmc_id='001', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/001_KeyChain_Dark.png', 'category_label': 'KeyChain', 'name': 'KeyChain (Dark)', 'required_level': 0})
        Background.objects.get_or_create(pmc_id='002', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/002_KeyChain_Light.png', 'category_label': 'KeyChain', 'name': 'KeyChain (Light)', 'required_level': 0})
        Background.objects.get_or_create(pmc_id='003', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/003_Discovery.png', 'category_label': 'General', 'name': 'Discovering KeyForge', 'required_level': 0})
        Background.objects.get_or_create(pmc_id='004', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/004_SloppyLabwork.png', 'category_label': 'Logos', 'name': 'Sloppy Labwork', 'required_level': 3})
        Background.objects.get_or_create(pmc_id='005', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/005_EnsignClark.png', 'category_label': 'Star Alliance', 'name': 'Ensign Clark', 'required_level': 13})
        Background.objects.get_or_create(pmc_id='006', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/006_PaleogeneSociety.png', 'category_label': 'Saurian', 'name': 'Paleogene Society', 'required_level': 13})
        Background.objects.get_or_create(pmc_id='007', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/007_OracleZan.png', 'category_label': 'Future Release', 'name': 'Oracle Zan', 'required_level': 13})
        Background.objects.get_or_create(pmc_id='008', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/008_HumbleRestraint.png', 'category_label': 'Sanctum', 'name': 'Humble Restraint', 'required_level': 12})
        Background.objects.get_or_create(pmc_id='009', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/009_Bwahah.png', 'category_label': 'General', 'name': 'Bwahah', 'required_level': 10})
        Background.objects.get_or_create(pmc_id='010', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/010_TheRedCotAComin.png', 'category_label': 'General', 'name': 'The Red CotA Comin\'', 'required_level': 7})
        Background.objects.get_or_create(pmc_id='011', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/011_SingingTheBlues.png', 'category_label': 'General', 'name': 'Sing the Blues oA', 'required_level': 7})
        Background.objects.get_or_create(pmc_id='012', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/012_TheAemberSky.png', 'category_label': 'Sets', 'name': 'The Æmber Sky', 'required_level': 8})
        Background.objects.get_or_create(pmc_id='013', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/013_GrimReminders.png', 'category_label': 'Sets', 'name': 'Grim Reminders', 'required_level': 8})
        Background.objects.get_or_create(pmc_id='014', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/014_EdgeOfTheWorld.png', 'category_label': 'Skyborn', 'name': 'Edge of the World', 'required_level': 14})
        Background.objects.get_or_create(pmc_id='015', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/015_BadPenny.png', 'category_label': 'Sanctum', 'name': 'Bad Penny', 'required_level': 3})
        Background.objects.get_or_create(pmc_id='016', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/016_Chaostadon.png', 'category_label': 'Saurian', 'name': 'Chaostadon', 'required_level': 4})
        Background.objects.get_or_create(pmc_id='017', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/017_TheOldBook.png', 'category_label': 'General', 'name': 'The Old Book', 'required_level': 2})
        Background.objects.get_or_create(pmc_id='018', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/018_ID.png', 'category_label': 'General', 'name': 'ID Check', 'required_level': 21})
        Background.objects.get_or_create(pmc_id='019', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/019_TheKeyraken.png', 'category_label': 'Adventures', 'name': 'The Keyraken', 'required_level': 17})
        Background.objects.get_or_create(pmc_id='020', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/020_KeymanderSpectralInvestigator.png',
                                         'category_label': 'KeyForge Community', 'name': 'Keymander: Spectral Investigator', 'required_level': 16})
        Background.objects.get_or_create(pmc_id='021', defaults={'src': 'https://static.sloppylabwork.com/pmc/backgrounds/021_KeymanderPrimordialSerpent.png',
                                         'category_label': 'KeyForge Community', 'name': 'Keymander: Primordial Serpent', 'required_level': 16})
        Background.objects.get_or_create(pmc_id='022', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/022_KeymanderWeirdo.png', 'category_label': 'KeyForge Community', 'name': 'Keymander: Weirdo', 'required_level': 16})
        Background.objects.get_or_create(pmc_id='023', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/023_MightMakesRight.png', 'category_label': 'Brobnar', 'name': 'Might Makes Right', 'required_level': 3})
        Background.objects.get_or_create(pmc_id='024', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/024_HauntedHouse.png', 'category_label': 'Geistoid', 'name': 'Haunted House', 'required_level': 5})
        Background.objects.get_or_create(pmc_id='025', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/025_BrendTheFanatic.png', 'category_label': 'Sanctum', 'name': 'Brend the Fanatic', 'required_level': 12})
        Background.objects.get_or_create(pmc_id='026', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/026_AbyssalConspiracy.png', 'category_label': 'Adventures', 'name': 'The Abyssal Conspiracy', 'required_level': 17})
        Background.objects.get_or_create(pmc_id='027', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/027_GettingStarted.png', 'category_label': 'General', 'name': 'Starting the Journey', 'required_level': 2})
        Background.objects.get_or_create(pmc_id='028', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/028_AmmoniaClouds.png', 'category_label': 'Mars', 'name': 'Ammonia Clouds', 'required_level': 3})
        Background.objects.get_or_create(pmc_id='029', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/029_CatenaFiend.png', 'category_label': 'Dis', 'name': 'Catena Fiend', 'required_level': 22})
        Background.objects.get_or_create(pmc_id='030', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/030_KelifiDragon.png', 'category_label': 'Brobnar', 'name': 'Kalifi Dragon', 'required_level': 11})
        Background.objects.get_or_create(pmc_id='031', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/031_DominatorBauble.png', 'category_label': 'Dis', 'name': 'Dominator Bauble', 'required_level': 11})
        Background.objects.get_or_create(pmc_id='032', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/032_CloudburstCommand.png', 'category_label': 'Skyborn', 'name': 'Cloudburst Command', 'required_level': 5})
        Background.objects.get_or_create(pmc_id='033', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/033_PunctuatedEquilibrium.png', 'category_label': 'Untamed', 'name': 'Punctuated Equilibrium', 'required_level': 13})
        Background.objects.get_or_create(pmc_id='034', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/034_FuzzyGruen.png', 'category_label': 'Untamed', 'name': 'Fuzzy Gruen', 'required_level': 3})
        Background.objects.get_or_create(pmc_id='035', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/035_DarkTidings.png', 'category_label': 'Sets', 'name': 'Dark Tidings', 'required_level': 8})
        Background.objects.get_or_create(pmc_id='036', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/036_Kaupe.png', 'category_label': 'Unfathomable', 'name': 'Kaupe', 'required_level': 4})
        Background.objects.get_or_create(pmc_id='037', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/037_Almsmaster.png', 'category_label': 'Sanctum', 'name': 'Almsmaster', 'required_level': 3})
        Background.objects.get_or_create(pmc_id='038', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/038_LibraryOfBabble.png', 'category_label': 'Logos', 'name': 'Library of Babble', 'required_level': 11})
        Background.objects.get_or_create(pmc_id='039', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/039_Memolith.png', 'category_label': 'General', 'name': 'Memolith', 'required_level': 10})
        Background.objects.get_or_create(pmc_id='040', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/040_DrXyloxxzlphrex.png', 'category_label': 'Mars', 'name': 'Dr. Xyloxxzlphrex', 'required_level': 12})
        Background.objects.get_or_create(pmc_id='041', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/041_UnlockedGateway.png', 'category_label': 'Dis', 'name': 'Unlocked Gateway', 'required_level': 3})
        Background.objects.get_or_create(pmc_id='042', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/042_VaultAssault.png', 'category_label': 'Sets', 'name': 'Vault Assault', 'required_level': 6})
        Background.objects.get_or_create(pmc_id='043', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/043_NicheMarket.png', 'category_label': 'Ekwidon', 'name': 'Niche Market', 'required_level': 14})
        Background.objects.get_or_create(pmc_id='044', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/044_MoonLightSpecial.png', 'category_label': 'Ekwidon', 'name': 'Moon Light Special', 'required_level': 5})
        Background.objects.get_or_create(pmc_id='045', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/045_EctoCharge.png', 'category_label': 'Geistoid', 'name': 'Ecto-Charge', 'required_level': 14})
        Background.objects.get_or_create(pmc_id='046', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/046_TacticalOfficerMoon.png', 'category_label': 'Star Alliance', 'name': 'Tactical Officer Moon', 'required_level': 4})
        Background.objects.get_or_create(pmc_id='047', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/047_TheChosenOne.png', 'category_label': 'Unfathomable', 'name': 'The Chosen One', 'required_level': 14})
        Background.objects.get_or_create(pmc_id='048', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/048_BurnTheStockpile.png', 'category_label': 'Brobnar', 'name': 'Burn the Stockpile', 'required_level': 22})
        Background.objects.get_or_create(pmc_id='049', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/049_NeonBlue.png', 'category_label': 'General', 'name': 'Neon Blue', 'required_level': 20})
        Background.objects.get_or_create(pmc_id='050', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/050_NeonGreen.png', 'category_label': 'General', 'name': 'Neon Green', 'required_level': 20})
        Background.objects.get_or_create(pmc_id='051', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/051_NeonPink.png', 'category_label': 'General', 'name': 'Neon Pink', 'required_level': 20})
        Background.objects.get_or_create(pmc_id='052', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/052_NeonYellow.png', 'category_label': 'General', 'name': 'Neon Yellow', 'required_level': 20})
        Background.objects.get_or_create(pmc_id='053', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/053_KeyChain_Bronze.png', 'category_label': 'KeyChain', 'name': 'KeyChain (Bronze)', 'required_level': 10})
        Background.objects.get_or_create(pmc_id='054', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/054_KeyChain_Silver.png', 'category_label': 'KeyChain', 'name': 'KeyChain (Silver)', 'required_level': 20})
        Background.objects.get_or_create(pmc_id='055', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/055_KeyChain_Gold.png', 'category_label': 'KeyChain', 'name': 'KeyChain (Gold)', 'required_level': 40})
        Background.objects.get_or_create(pmc_id='056', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/056_KeyChain_Ascension.png', 'category_label': 'KeyChain', 'name': 'KeyChain (Ascension)', 'required_level': 50})
        Background.objects.get_or_create(pmc_id='057', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/057_VindicationOutpost.png', 'category_label': 'Redemption', 'name': 'Vindication Outpost', 'required_level': 13})
        Background.objects.get_or_create(pmc_id='058', defaults={
                                         'src': 'https://static.sloppylabwork.com/pmc/backgrounds/058_RedeemerAmara.png', 'category_label': 'Redemption', 'name': 'Redeemer Amara', 'required_level': 5})
