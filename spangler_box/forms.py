from django import forms
from django.utils.translation import gettext_lazy as _
from .models import SecretChainTemplate


class SelectTemplateForm(forms.Form):
    template = forms.ModelChoiceField(
        queryset=SecretChainTemplate.objects.all(), label=_('Template'))
