from django import forms
from .models import Tournament, TournamentRegistration


# TODO: Vaiidate players_info data

class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ['name', 'date', 'tournament_format']


def make_sign_up_form(user, tournament):
    qs_user_deck_registrations = user.deck_registrations.filter(is_active=True)
    fields = {
        'deck0': forms.ModelChoiceField(queryset=qs_user_deck_registrations, label='Deck 1')
    }
    return type('SignUpForm', (forms.BaseForm,), {'base_fields': fields})
