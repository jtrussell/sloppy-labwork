from django import forms
from .models import Event, PmcProfile
from .models import PlaygroupMember
from .models import EventFormat
from django.utils.translation import gettext_lazy as _


class EventForm(forms.ModelForm):
    results_file = forms.FileField(required=True)
    format = forms.ModelChoiceField(
        queryset=EventFormat.objects.all(),
        empty_label=_('Other'),
        required=False
    )

    class Meta:
        model = Event
        fields = ('name', 'start_date', 'format', 'player_count')
        labels = {
            'name': _('Event Name'),
            'start_date': _('Event Date'),
            'player_count': _('Player Count'),
        }
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'player_count': forms.NumberInput(attrs={
                'min': 0,
                'placeholder': _('Automatic')
            }),
        }

    def save(self, commit=True):
        event = super(EventForm, self).save(commit=commit)
        return event


class PlaygroupMemberForm(forms.ModelForm):
    class Meta:
        model = PlaygroupMember
        fields = ('nickname',)


class PmcProfileForm(forms.ModelForm):
    class Meta:
        model = PmcProfile
        fields = ('tagline',)
