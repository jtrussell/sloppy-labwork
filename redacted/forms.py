from re import search
from django import forms
from django.utils.translation import gettext_lazy as _

EXPANSION_CHOICES = [
    (None, _('Any')),
    (341, _('Call of the Archons')),
    (435, _('Age of Ascension')),
    (452, _('Worlds Collide')),
    (479, _('Mass Mutation')),
    (496, _('Dark Tidings')),
    (600, _('Winds of Exchange')),
    (601, _('Unchained 2022')),
    (609, _('Vault Masters 2023')),
    (700, _('Grim Reminders')),
    (722, _('Menagerie')),
    (737, _('Vault Masters 2024')),
    (800, _('Æmber Skies')),
    (855, _('Tokens of Change')),
    (874, _('More Mutation')),
    (886, _('Prophetic Visions')),
    (907, _('Discovery')),
    (918, _('Crucible Clash')),
]


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
