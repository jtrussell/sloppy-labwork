from django.contrib import admin
from datetime import datetime
from .models import DeckRegistration


def verify(modeladmin, request, queryset):
    queryset.update(
        has_photo_verification=True,
        verified_on=datetime.now(),
        verified_by=request.user
    )


def unverify(modeladmin, request, queryset):
    queryset.update(
        has_photo_verification=False,
        verified_on=None,
        verified_by=None
    )


class DeckRegistrationAdmin(admin.ModelAdmin):
    list_display = ('deck', 'user', 'has_photo_verification', 'created_on')
    list_filter = ('has_photo_verification',)
    search_fields = ['use', 'deck']
    ordering = ('has_photo_verification', 'created_on')
    actions = (verify, unverify)


admin.site.register(DeckRegistration, DeckRegistrationAdmin)
