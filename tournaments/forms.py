from django import forms
from .models import Tournament
from register.models import DeckRegistration


# TODO: Validate players_info data

class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ['name', 'date', 'tournament_format']


def make_sign_up_form(user, tournament):
    qs_user_deck_registrations = user.deck_registrations.filter(
        status=DeckRegistration.Status.VERIFIED_ACTIVE)
    fields = {
        'deck0': forms.ModelChoiceField(queryset=qs_user_deck_registrations, label='Deck 1', required=False)
    }
    return type('SignUpForm', (forms.BaseForm,), {'base_fields': fields})
