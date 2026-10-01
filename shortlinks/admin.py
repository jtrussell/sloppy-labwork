from django.contrib import admin
from .models import ShortLink


@admin.register(ShortLink)
class ShortLinkAdmin(admin.ModelAdmin):
    list_display = ['slug', 'target_url', 'response_type',
                    'is_active', 'hit_count', 'updated_on']
    list_filter = ['response_type', 'is_active']
    search_fields = ['slug', 'target_url']
    readonly_fields = ['hit_count', 'created_on', 'updated_on']
