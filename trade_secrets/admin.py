from django.contrib import admin

from .models import PlayResult, Session, SessionDeck, SessionTemplate, StepSubmission, TemplateStep


class TemplateStepInline(admin.TabularInline):
    model = TemplateStep
    extra = 0
    fields = ['order', 'action', 'quantity', 'played_deck_rule']

    def is_template_in_use(self, template):
        return template is not None and template.sessions.exists()

    def has_add_permission(self, request, obj=None):
        return not self.is_template_in_use(obj) and super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return not self.is_template_in_use(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not self.is_template_in_use(obj) and super().has_delete_permission(request, obj)


@admin.register(SessionTemplate)
class SessionTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'system_key', 'code', 'archived_on', 'created_on']
    list_filter = ['archived_on', 'created_on']
    search_fields = ['name', 'owner__username', 'code', 'system_key']
    readonly_fields = ['code', 'created_on']
    inlines = [TemplateStepInline]


class SessionDeckInline(admin.TabularInline):
    model = SessionDeck
    extra = 0
    raw_id_fields = ['deck', 'source_version']


class PlayResultInline(admin.TabularInline):
    model = PlayResult
    extra = 0
    raw_id_fields = ['step', 'updated_by']


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['code', 'template', 'host', 'guest', 'revealed_step_count', 'created_on']
    list_filter = ['created_on']
    search_fields = ['code', 'host__username', 'guest__username', 'template__name']
    readonly_fields = ['code', 'revealed_step_count', 'version', 'created_on', 'updated_on']
    raw_id_fields = ['host', 'guest', 'template']
    inlines = [SessionDeckInline, PlayResultInline]


@admin.register(StepSubmission)
class StepSubmissionAdmin(admin.ModelAdmin):
    list_display = ['session', 'step', 'seat', 'submitted_by', 'updated_on']
    raw_id_fields = ['session', 'step', 'submitted_by']
    filter_horizontal = ['decks']
