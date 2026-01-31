from django.contrib import admin
from .models import Badge, EventTag, LeaderboardLog, Playgroup, PlaygroupEvent, PlaygroupLeaderboard, PlaygroupType, PmcProfile, RankingPointsMap, RankingPointsMapVersion, UserBadge
from .models import PlaygroupMember
from .models import Venue, PlaygroupVenue
from .models import Event
from .models import EventResult
from .models import RankingPoints
from .models import EventFormat
from .models import LeaderboardSeason
from .models import LeaderboardSeasonPeriod
from .models import Leaderboard
from .models import PlayerRank
from .models import LevelBreakpoint
from .models import Avatar
from .models import Background
from .models import BackgroundCategory
from .models import AvatarCategory
from .models import PlaygroupJoinRequest
from .models import Trophy, UserTrophy, AwardCredit, Achievement, AchievementTier, UserAchievementTier
from .models import EventResultDeck


class PlaygroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'primary_venue', 'created_on')
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'primary_venue':
            object_id = request.resolver_match.kwargs.get('object_id')
            if object_id:
                kwargs['queryset'] = Venue.objects.filter(
                    playgroup_venues__playgroup_id=object_id
                )
            else:
                kwargs['queryset'] = Venue.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class PlaygroupMemberAdmin(admin.ModelAdmin):
    list_display = ('playgroup', 'user', 'nickname', 'joined_on', 'is_staff')
    search_fields = ['playgroup', 'user', 'nickname']
    list_filter = ('is_staff',)


class EventTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_eo_assignable')
    search_fields = ['name', 'slug']
    list_filter = ('is_eo_assignable',)
    prepopulated_fields = {'slug': ('name',)}


class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'is_excluded_from_global_rankings')
    search_fields = ['name']
    list_filter = ('start_date', 'is_excluded_from_global_rankings', 'tags')
    filter_horizontal = ('tags',)


class EventResultAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'finishing_position',
                    'num_wins', 'num_losses')
    search_fields = ['event', 'user']
    list_filter = ('event',)


class RankingPointsMapVersionAdmin(admin.ModelAdmin):
    list_display = ('name', 'effective_on')
    search_fields = ['name']
    list_filter = ()


class RankingPointsMapAdmin(admin.ModelAdmin):
    list_display = ('version', 'max_players', 'finishing_position', 'points')
    search_fields = ['max_players']
    list_filter = ('max_players', 'version')


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
    list_display = ('name', 'season', 'start_date', 'is_locked')
    search_fields = ['season']
    list_filter = ('season', 'is_locked')
    readonly_fields = ('is_locked',)


class LeaderboardAdmin(admin.ModelAdmin):
    list_display = ('name', 'period_frequency')
    search_fields = ['name']
    list_filter = ('name',)


class PlayerRankAdmin(admin.ModelAdmin):
    list_display = ('leaderboard', 'playgroup',
                    'user', 'rank', 'total_points', 'num_results')
    search_fields = ['leaderboard', 'playgroup', 'user']
    list_filter = ('leaderboard',)


class LeaderboardLogAdmin(admin.ModelAdmin):
    list_display = ('leaderboard', 'action', 'action_date')
    search_fields = ['leaderboard']
    list_filter = ('leaderboard',)


class PlaygroupEventAdmin(admin.ModelAdmin):
    list_display = ('playgroup', 'event',)
    search_fields = ['playgroup', 'event']
    list_filter = ()


class PmcProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'mv_username',)
    search_fields = ['user__username', 'mv_username']
    list_filter = ()


class LevelBreakpointAdmin(admin.ModelAdmin):
    list_display = ('level', 'required_xp')
    search_fields = ['level']
    list_filter = ()


class AvatarAdmin(admin.ModelAdmin):
    list_display = ('pmc_id', 'name', 'category', 'required_level')
    search_fields = ['pmc_id', 'name']
    list_filter = ('category',)


class BackgroundAdmin(admin.ModelAdmin):
    list_display = ('pmc_id', 'name', 'category', 'required_level')
    search_fields = ['pmc_id', 'name']
    list_filter = ('category',)


class AvatarCategoryAdmin(admin.ModelAdmin):
    list_display = ('sort_order', 'name', 'is_hidden')
    search_fields = ['name']
    list_filter = ()


class BackgroundCategoryAdmin(admin.ModelAdmin):
    list_display = ('sort_order', 'name', 'is_hidden')
    search_fields = ['name']
    list_filter = ()


class PlaygroupJoinRequestAdmin(admin.ModelAdmin):
    list_display = ('playgroup', 'user', 'created_on', 'status')
    search_fields = ['playgroup', 'user']
    list_filter = ('playgroup',)


class VenueAdmin(admin.ModelAdmin):
    list_display = ('name', 'venue_type', 'city', 'state_province', 'country', 'has_coordinates', 'created_on')
    search_fields = ['name', 'address', 'city', 'state_province', 'country']
    list_filter = ('venue_type', 'country')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('formatted_address', 'city', 'state_province', 'country', 'country_code', 'postal_code', 'latitude', 'longitude', 'created_on', 'updated_on')
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'venue_type', 'address', 'website', 'notes')
        }),
        ('Geocoded Data', {
            'fields': ('formatted_address', 'city', 'state_province', 'country', 'country_code', 'postal_code', 'latitude', 'longitude'),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_on', 'updated_on'),
            'classes': ('collapse',),
        }),
    )

    def has_coordinates(self, obj):
        return obj.has_coordinates()
    has_coordinates.boolean = True


class PlaygroupVenueAdmin(admin.ModelAdmin):
    list_display = ('playgroup', 'venue', 'added_on')
    search_fields = ['playgroup__name', 'venue__name']
    list_filter = ('playgroup',)


class BadgeAdmin(admin.ModelAdmin):
    list_display = ('pmc_id', 'name', 'reward_category', 'is_hidden')
    search_fields = ['name', 'pmc_id']
    list_filter = ()


class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ('user', 'badge', 'date_awarded')
    search_fields = ['user__username', 'badge']
    list_filter = ()


class TrophyAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'sort_order', 'is_hidden')
    search_fields = ['name']
    list_filter = ()


class UserTrophyAdmin(admin.ModelAdmin):
    list_display = ('user', 'trophy')
    search_fields = ['user__username', 'trophy']
    list_filter = ()


class AwardCriteriaAdmin(admin.ModelAdmin):
    list_display = ('type',)
    search_fields = []
    list_filter = ()


class AwardCreditAdmin(admin.ModelAdmin):
    list_display = ('user', 'criteria', 'added_on')
    search_fields = ['user__username']
    list_filter = ()


class AchievementAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'sort_order', 'is_hidden')
    search_fields = ['name']
    list_filter = ()


class AchievementTierAdmin(admin.ModelAdmin):
    list_display = ('achievement', 'tier', 'criteria_value')
    search_fields = ['achievement__name']
    list_filter = ('achievement',)


class UserAchievementTierAdmin(admin.ModelAdmin):
    list_display = ('user', 'achievement_tier', 'date_awarded')
    search_fields = ['user__username']
    list_filter = ('achievement_tier__achievement',)


class EventResultDeckAdmin(admin.ModelAdmin):
    list_display = ('deck', 'event_result__event')
    search_fields = ['deck__name', 'event_result__event__name']
    list_filter = ()


class PlaygroupLeaderboardAdmin(admin.ModelAdmin):
    list_display = ('playgroup', 'leaderboard')
    search_fields = ['playgroup__name', 'leaderboard__name']
    list_filter = ()


class PlaygroupTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ['name']
    list_filter = ()


admin.site.register(Playgroup, PlaygroupAdmin)
admin.site.register(PlaygroupMember, PlaygroupMemberAdmin)
admin.site.register(EventTag, EventTagAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(EventResult, EventResultAdmin)
admin.site.register(RankingPointsMapVersion, RankingPointsMapVersionAdmin)
admin.site.register(RankingPointsMap, RankingPointsMapAdmin)
admin.site.register(RankingPoints, RankingPointsAdmin)
admin.site.register(EventFormat, EventFormatAdmin)
admin.site.register(LeaderboardSeason, LeaderboardSeasonAdmin)
admin.site.register(LeaderboardSeasonPeriod, LeaderboardSeasonPeriodAdmin)
admin.site.register(Leaderboard, LeaderboardAdmin)
admin.site.register(PlayerRank, PlayerRankAdmin)
admin.site.register(LeaderboardLog, LeaderboardLogAdmin)
admin.site.register(PlaygroupEvent, PlaygroupEventAdmin)
admin.site.register(PmcProfile, PmcProfileAdmin)
admin.site.register(LevelBreakpoint, LevelBreakpointAdmin)
admin.site.register(Avatar, AvatarAdmin)
admin.site.register(Background, BackgroundAdmin)
admin.site.register(AvatarCategory, AvatarCategoryAdmin)
admin.site.register(BackgroundCategory, BackgroundCategoryAdmin)
admin.site.register(PlaygroupJoinRequest, PlaygroupJoinRequestAdmin)
admin.site.register(Badge, BadgeAdmin)
admin.site.register(UserBadge, UserBadgeAdmin)
admin.site.register(Trophy, TrophyAdmin)
admin.site.register(UserTrophy, UserTrophyAdmin)
admin.site.register(AwardCredit, AwardCreditAdmin)
admin.site.register(Achievement, AchievementAdmin)
admin.site.register(AchievementTier, AchievementTierAdmin)
admin.site.register(UserAchievementTier, UserAchievementTierAdmin)
admin.site.register(EventResultDeck, EventResultDeckAdmin)
admin.site.register(PlaygroupLeaderboard, PlaygroupLeaderboardAdmin)
admin.site.register(PlaygroupType, PlaygroupTypeAdmin)
admin.site.register(Venue, VenueAdmin)
admin.site.register(PlaygroupVenue, PlaygroupVenueAdmin)
