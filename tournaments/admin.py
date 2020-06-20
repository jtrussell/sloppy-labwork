from django.contrib import admin
from .models import Tournament


class TournamentAdmin(admin.ModelAdmin):
    list_display = ('name', 'date')
    search_fields = ['name', 'date']


admin.site.register(Tournament, TournamentAdmin)
