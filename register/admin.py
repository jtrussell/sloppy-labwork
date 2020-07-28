from django.contrib import admin
from datetime import datetime
from .models import DeckRegistration


def verify(modeladmin, request, queryset):
    queryset.update(
        status=DeckRegistration.Status.VERIFIED_ACTIVE,
        verified_on=datetime.now(),
        verified_by=request.user
    )


def unverify(modeladmin, request, queryset):
    queryset.update(
        status=DeckRegistration.Status.PENDING,
        verified_on=None,
        verified_by=None
    )


class DeckRegistrationAdmin(admin.ModelAdmin):
    list_display = ('deck', 'user', 'status', 'created_on')
    list_filter = ('status',)
    search_fields = ['user', 'deck']
    ordering = ('status', 'created_on')
    actions = (verify, unverify)


admin.site.register(DeckRegistration, DeckRegistrationAdmin)
