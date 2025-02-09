from django import forms
from .models import Event
from .models import PlaygroupMember
from django.utils.translation import gettext_lazy as _


class EventForm(forms.ModelForm):
    results_file = forms.FileField(required=True)

    class Meta:
        model = Event
        fields = ('name', 'start_date', 'player_count')
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
        fields = ('nickname', 'house_flair', 'tagline',)
