from django import forms
from django.utils.translation import gettext_lazy as _
from decks.models import Set

SET_GROUP_CHOICES = [
    ('', _('Any')),
    ('legacy', _('Legacy')),
    ('modern', _('Modern')),
    ('tournament', _('Tournament')),
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
    expansion = forms.ChoiceField(
        required=False,
        label=_('Set'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        set_choices = [(str(s.id), s.name) for s in Set.objects.all()]
        self.fields['expansion'].choices = SET_GROUP_CHOICES + set_choices
