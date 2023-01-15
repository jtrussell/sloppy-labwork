from django.contrib import admin

# Register your models here.
from deck_simulator.models import GeneratedDeck


class GeneratedDeckAdmin(admin.ModelAdmin):
    list_display = ['name', 'uid']


admin.site.register(GeneratedDeck, GeneratedDeckAdmin)
