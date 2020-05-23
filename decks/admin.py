from django.contrib import admin
from .models import Deck


class DeckAdmin(admin.ModelAdmin):
    list_display = ('name', 'added_on')
    search_fields = ['id', 'name']


admin.site.register(Deck, DeckAdmin)
