from django.contrib import admin
from .models import Tournament, TournamentFormat, TournamentRegistration


class TournamentAdmin(admin.ModelAdmin):
    list_display = ['name', 'date']
    search_fields = ['name', 'date']


class TournamentFormatAdmin(admin.ModelAdmin):
    list_display = ['name', 'decks_per_player']
    search_fields = ['name']


class TournamentRegistrationAdmin(admin.ModelAdmin):
    list_display = ['player']
    search_fields = ['player', 'decks']


admin.site.register(Tournament, TournamentAdmin)
admin.site.register(TournamentFormat, TournamentFormatAdmin)
admin.site.register(TournamentRegistration, TournamentRegistrationAdmin)
