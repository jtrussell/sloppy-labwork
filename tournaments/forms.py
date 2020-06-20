from django import forms
from .models import Tournament


# TODO: Vaiidate players_info data

class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ['name', 'date', 'players_info']
