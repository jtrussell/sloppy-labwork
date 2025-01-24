from django.contrib import admin
from .models import Playgroup
from .models import PlaygroupMember
from .models import Event
from .models import EventResult


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


admin.site.register(Playgroup, PlaygroupAdmin)
admin.site.register(PlaygroupMember, PlaygroupMemberAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(EventResult, EventResultAdmin)
