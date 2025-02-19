from django.contrib import admin
from .models import LeaderboardLog, Playgroup, PlaygroupEvent, RankingPointsMap
from .models import PlaygroupMember
from .models import Event
from .models import EventResult
from .models import RankingPoints
from .models import EventFormat
from .models import LeaderboardSeason
from .models import LeaderboardSeasonPeriod
from .models import Leaderboard
from .models import PlayerRank


class PlaygroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_on')
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


class PlaygroupMemberAdmin(admin.ModelAdmin):
    list_display = ('playgroup', 'user', 'nickname', 'joined_on', 'is_staff')
    search_fields = ['playgroup', 'user', 'nickname']
    list_filter = ('is_staff',)


class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date')
    search_fields = ['name']
    list_filter = ('start_date',)


class EventResultAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'finishing_position',
                    'num_wins', 'num_losses')
    search_fields = ['event', 'user']
    list_filter = ('event',)


class RankingPointsMapAdmin(admin.ModelAdmin):
    list_display = ('max_players', 'finishing_position', 'points')
    search_fields = ['max_players']
    list_filter = ('max_players',)


class RankingPointsAdmin(admin.ModelAdmin):
    list_display = ('result', 'points')
    search_fields = ['result__event']
    list_filter = ('result__event',)


class EventFormatAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ['name']
    list_filter = ('name',)


class LeaderboardSeasonAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ['name']


class LeaderboardSeasonPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'season', 'start_date')
    search_fields = ['season']
    list_filter = ('season',)


class LeaderboardAdmin(admin.ModelAdmin):
    list_display = ('name', 'period_frequency')
    search_fields = ['name']
    list_filter = ('name',)


class PlayerRankAdmin(admin.ModelAdmin):
    list_display = ('leaderboard', 'playgroup',
                    'user', 'rank', 'average_points')
    search_fields = ['leaderboard', 'playgrou', 'user']
    list_filter = ('leaderboard',)


class LeaderboardLogAdmin(admin.ModelAdmin):
    list_display = ('leaderboard', 'action', 'action_date')
    search_fields = ['leaderboard']
    list_filter = ('leaderboard',)


class PlaygroupEventAdmin(admin.ModelAdmin):
    list_display = ('playgroup', 'event',)
    search_fields = ['playgroup', 'event']
    list_filter = ()


admin.site.register(Playgroup, PlaygroupAdmin)
admin.site.register(PlaygroupMember, PlaygroupMemberAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(EventResult, EventResultAdmin)
admin.site.register(RankingPointsMap, RankingPointsMapAdmin)
admin.site.register(RankingPoints, RankingPointsAdmin)
admin.site.register(EventFormat, EventFormatAdmin)
admin.site.register(LeaderboardSeason, LeaderboardSeasonAdmin)
admin.site.register(LeaderboardSeasonPeriod, LeaderboardSeasonPeriodAdmin)
admin.site.register(Leaderboard, LeaderboardAdmin)
admin.site.register(PlayerRank, PlayerRankAdmin)
admin.site.register(LeaderboardLog, LeaderboardLogAdmin)
admin.site.register(PlaygroupEvent, PlaygroupEventAdmin)
