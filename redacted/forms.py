from cProfile import label
from django import forms
from django.utils.translation import gettext_lazy as _


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
