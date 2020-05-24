from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decks.models import Deck
import uuid


def validate_master_vault_url(value):
    master_vault_id = Deck.get_id_from_master_vault_url(value)
    try:
        master_vault_id = uuid.UUID(master_vault_id)
    except ValueError:
        raise(ValidationError(
            _('Master vault link is invalid'),
            code='invalid'
        ))


class RegiseterNewDeckForm(forms.Form):
    master_vault_link = forms.CharField(
        max_length=200,
        validators=[validate_master_vault_url],
        widget=forms.TextInput(
            attrs={
                'placeholder': 'https://www.keyforgegame.com/deck-details/2dea0ea6-e371-4b9a-826c-28f6620ef550'}
        ))
    verification_photo = forms.FileField()
