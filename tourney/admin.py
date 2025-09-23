from django.contrib import admin
from .models import (
    Tournament, Player, TournamentAdmin, Stage, StageRankingCriteria, Group, StagePlayer,
    Round, Match, MatchResult, TournamentActionLog
)


@admin.register(Tournament)
class TournamentModelAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'is_accepting_registrations', 'created_on']
    list_filter = ['is_accepting_registrations', 'created_on']
    search_fields = ['name', 'owner__username']
    readonly_fields = ['created_on', 'updated_on']


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ['get_display_name', 'user', 'tournament', 'status', 'created_on']
    list_filter = ['status', 'tournament', 'created_on']
    search_fields = ['user__username', 'nickname', 'tournament__name']


@admin.register(TournamentAdmin)
class TournamentAdminModelAdmin(admin.ModelAdmin):
    list_display = ['user', 'tournament', 'created_on']
    list_filter = ['tournament', 'created_on']
    search_fields = ['user__username', 'tournament__name']


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ['name', 'tournament', 'order', 'pairing_strategy', 'created_on']
    list_filter = ['pairing_strategy', 'created_on']
    search_fields = ['name', 'tournament__name']


@admin.register(StageRankingCriteria)
class StageRankingCriteriaAdmin(admin.ModelAdmin):
    list_display = ['stage', 'criterion_key', 'order', 'get_criterion_name']
    list_filter = ['criterion_key', 'stage__tournament']
    search_fields = ['stage__name', 'stage__tournament__name', 'criterion_key']
    ordering = ['stage', 'order']

    def get_criterion_name(self, obj):
        criterion = obj.get_criterion_object()
        return criterion.get_name() if criterion else obj.criterion_key
    get_criterion_name.short_description = 'Criterion Name'


@admin.register(StagePlayer)
class StagePlayerAdmin(admin.ModelAdmin):
    list_display = ['player', 'stage', 'seed', 'group']
    list_filter = ['stage', 'group']
    search_fields = ['player__user__username', 'player__nickname', 'stage__name']


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ['stage', 'order', 'created_on']
    list_filter = ['stage', 'created_on']
    search_fields = ['stage__name', 'stage__tournament__name']


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ['round', 'player_one', 'player_two', 'has_result', 'created_on']
    list_filter = ['round__stage', 'created_on']
    search_fields = ['round__stage__name', 'player_one__player__user__username', 'player_two__player__user__username']


@admin.register(MatchResult)
class MatchResultAdmin(admin.ModelAdmin):
    list_display = ['match', 'winner', 'player_one_score', 'player_two_score', 'created_on']
    list_filter = ['created_on']
    search_fields = ['match__round__stage__name', 'winner__player__user__username']


@admin.register(TournamentActionLog)
class TournamentActionLogAdmin(admin.ModelAdmin):
    list_display = ['tournament', 'user', 'action_type', 'created_on']
    list_filter = ['action_type', 'tournament', 'created_on']
    search_fields = ['tournament__name', 'user__username', 'description']
    readonly_fields = ['created_on']
