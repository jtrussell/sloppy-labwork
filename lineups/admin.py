from django.contrib import admin
from .models import Lineup, LineupNote, LineupVersion, LineupVersionNote, LineupVersionDeck


class LineupNoteInline(admin.TabularInline):
    model = LineupNote
    extra = 0
    readonly_fields = ['created_on', 'updated_on']


class LineupVersionInline(admin.TabularInline):
    model = LineupVersion
    extra = 0
    readonly_fields = ['code', 'created_on']
    fields = ['code', 'name', 'visibility_override', 'sort_order', 'created_on']


@admin.register(Lineup)
class LineupAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'code', 'visibility', 'format', 'created_on', 'updated_on']
    list_filter = ['visibility', 'format', 'created_on']
    search_fields = ['name', 'owner__username', 'code']
    readonly_fields = ['code', 'created_on', 'updated_on']
    inlines = [LineupVersionInline, LineupNoteInline]


@admin.register(LineupNote)
class LineupNoteAdmin(admin.ModelAdmin):
    list_display = ['lineup', 'text_preview', 'created_on']
    list_filter = ['created_on']
    search_fields = ['lineup__name', 'text']
    readonly_fields = ['created_on', 'updated_on']

    def text_preview(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Text'


class LineupVersionNoteInline(admin.TabularInline):
    model = LineupVersionNote
    extra = 0
    readonly_fields = ['created_on', 'updated_on']


class LineupVersionDeckInline(admin.TabularInline):
    model = LineupVersionDeck
    extra = 0
    raw_id_fields = ['deck']


@admin.register(LineupVersion)
class LineupVersionAdmin(admin.ModelAdmin):
    list_display = ['name', 'lineup', 'code', 'visibility_override', 'sort_order', 'created_on']
    list_filter = ['visibility_override', 'created_on']
    search_fields = ['name', 'lineup__name', 'code']
    readonly_fields = ['code', 'created_on', 'updated_on']
    inlines = [LineupVersionDeckInline, LineupVersionNoteInline]


@admin.register(LineupVersionNote)
class LineupVersionNoteAdmin(admin.ModelAdmin):
    list_display = ['version', 'text_preview', 'created_on']
    list_filter = ['created_on']
    search_fields = ['version__name', 'text']
    readonly_fields = ['created_on', 'updated_on']

    def text_preview(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Text'


@admin.register(LineupVersionDeck)
class LineupVersionDeckAdmin(admin.ModelAdmin):
    list_display = ['version', 'deck', 'sort_order']
    list_filter = ['version__lineup']
    search_fields = ['version__name', 'deck__name']
    raw_id_fields = ['deck']
