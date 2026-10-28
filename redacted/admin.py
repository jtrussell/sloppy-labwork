from django.contrib import admin
from .models import FallbackCollection


class FallbackCollectionAdmin(admin.ModelAdmin):
    list_display = ('dok_username', 'is_active')
    list_editable = ('is_active',)
    list_filter = ('is_active',)
    search_fields = ['dok_username']


admin.site.register(FallbackCollection, FallbackCollectionAdmin)
