from django.core.management.base import BaseCommand
from pmc.models import LevelBreakpoint, EventFormat, Leaderboard, LeaderboardSeason, LeaderboardSeasonPeriod
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
        EventFormat.objects.get_or_create(name='Adaptive')
        EventFormat.objects.get_or_create(name='Archon')
        EventFormat.objects.get_or_create(name='Sealed')

    def make_ranking_points_map(self):
        pass
