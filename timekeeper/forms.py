from django import forms
from .models import CountdownTimer


class TimerCreateForm(forms.ModelForm):
    minutes = forms.IntegerField(
        min_value=0,
        max_value=999,
        initial=50,
        help_text='Duration in minutes'
    )

    class Meta:
        model = CountdownTimer
        fields = ['name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].initial = 'Timer'

    def save(self, commit=True):
        instance = super().save(commit=False)
        minutes = self.cleaned_data.get('minutes', 0)
        instance.pause_time_remaining_seconds = minutes * 60
        if commit:
            instance.save()
        return instance
