from django import forms
from django.utils.translation import gettext_lazy as _
from .models import SecretChainLink, SecretChainTemplate


class SelectTemplateForm(forms.Form):
    template = forms.ModelChoiceField(
        queryset=SecretChainTemplate.objects.all(), required=True, label=_('Template'), initial=1)


class AddDecksForm(forms.Form):
    deck_ids = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6, 'style': 'height: unset;'}),
        label=_('Deck links'),
        help_text=_(
            'Enter deck links separated by commas, spaces, or new lines'),
        required=True)


class SecretChainLinkResponseFormService():
    @staticmethod
    def get_form_for_link(link):
        if link.kind == SecretChainLink.Kind.ADD_LIST_OF_KF_DECKS:
            return AddDecksForm()
        else:
            raise ValueError('Unknown link kind')
