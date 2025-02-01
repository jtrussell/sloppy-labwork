from django import forms
from .models import Event, Playgroup
from .models import PlaygroupMember


class EventForm(forms.ModelForm):
    results_file = forms.FileField(required=True)

    class Meta:
        model = Event
        fields = ('name', 'start_date',)
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
        }

    # def clean_results_file(self):
    #    results_file = self.cleaned_data.get('results_file')
    #    if not results_file.name.endswith('.csv'):
    #        raise forms.ValidationError('Only CSV files are supported')
    #    return results_file

    def save(self, commit=True):
        event = super(EventForm, self).save(commit=commit)
        return event


class PlaygroupMemberForm(forms.ModelForm):
    class Meta:
        model = PlaygroupMember
        fields = ('nickname', 'house_flair', 'tagline',)
