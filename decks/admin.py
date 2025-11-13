from django.contrib import admin
from .models import Deck, Set, House


class DeckAdmin(admin.ModelAdmin):
    list_display = ('name', 'added_on')
    search_fields = ['id', 'name']


class SetAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ['id', 'name']


class HouseAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ['name']


admin.site.register(Deck, DeckAdmin)
admin.site.register(Set, SetAdmin)
admin.site.register(House, HouseAdmin)
