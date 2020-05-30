from django.contrib import admin
from datetime import datetime
from .models import DeckRegistration


def verify(modeladmin, request, queryset):
    queryset.update(
        is_verified=True,
        verified_on=datetime.now(),
        verified_by=request.user
    )


def unverify(modeladmin, request, queryset):
    queryset.update(
        is_verified=False,
        verified_on=None,
        verified_by=None
    )


class DeckRegistrationAdmin(admin.ModelAdmin):
    list_display = ('deck', 'user', 'is_verified', 'created_on')
    list_filter = ('is_verified',)
    search_fields = ['user', 'deck']
    ordering = ('is_verified', 'created_on')
    actions = (verify, unverify)


admin.site.register(DeckRegistration, DeckRegistrationAdmin)
