from re import search
from django import forms
from django.utils.translation import gettext_lazy as _
from decks.models import EXPANSION_CHOICES


class RandomDecksFromDokForm(forms.Form):
    dok_username = forms.CharField(max_length=100, label=_('DoK username'))
    min_sas = forms.IntegerField(
        required=False,
        label=_('Min SAS'),
        widget=forms.NumberInput(
            attrs={
                'placeholder': _('Any')}
        ))
    max_sas = forms.IntegerField(
        required=False,
        label=_('Max SAS'),
        widget=forms.NumberInput(
            attrs={
                'placeholder': _('Any')}
        ))
    expansion = forms.IntegerField(
        required=False,
        widget=forms.Select(
            choices=EXPANSION_CHOICES)
    )
