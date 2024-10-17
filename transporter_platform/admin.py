from django.contrib import admin

from transporter_platform.models import MatchRequest, PastMatch, PodPlayer


class PodPlayerAdmin(admin.ModelAdmin):
    list_display = ('user', 'user_handle', 'pod')
    list_filter = ('pod',)
    search_fields = ['user', 'user_handle']
    ordering = ('pod', 'user_handle')


class PastMatchAdmin(admin.ModelAdmin):
    list_display = ('player', 'opponent')
    search_fields = ['player', 'opponent']
    ordering = ('player', 'opponent')


class MatchRequestAdmin(admin.ModelAdmin):
    list_display = ('player', 'created_on', 'completed_by', 'is_cancelled')
    search_fields = ['player']
    ordering = ('created_on', 'player')


admin.site.register(PodPlayer, PodPlayerAdmin)
admin.site.register(PastMatch, PastMatchAdmin)
admin.site.register(MatchRequest, MatchRequestAdmin)
