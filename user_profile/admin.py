from django.contrib import admin
from .models import UserProfile


class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('discord_handle', 'challonge_handle', 'tco_handle')
    search_fields = ['discord_handle', 'challonge_handle', 'tco_handle']
    ordering = ('tco_handle',)


admin.site.register(UserProfile, UserProfileAdmin)
