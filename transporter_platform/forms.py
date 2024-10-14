from django import forms
from django.utils.translation import gettext_lazy as _

ACTION_CREATE = 0
ACTION_CANCEL = 1
ACTION_RECORD_MATCH = 2


class KagiLivePlayForm(forms.Form):
    action = forms.IntegerField(
        required=True,
        widget=forms.HiddenInput(),
    )
