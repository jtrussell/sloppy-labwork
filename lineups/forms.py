from django import forms
from .models import Lineup, LineupNote, LineupVersion, LineupVersionNote, LineupVersionDeck
from pmc.models import EventFormat
from decks.models import Deck


class LineupForm(forms.ModelForm):
    class Meta:
        model = Lineup
        fields = ['name', 'description', 'visibility', 'format']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['format'].queryset = EventFormat.objects.all()
        self.fields['format'].required = False
        self.fields['format'].empty_label = 'No format'


class LineupNoteForm(forms.ModelForm):
    class Meta:
        model = LineupNote
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Add a note...'}),
        }


class LineupVersionForm(forms.ModelForm):
    class Meta:
        model = LineupVersion
        fields = ['name', 'description', 'visibility_override']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['visibility_override'].required = False
        self.fields['visibility_override'].empty_label = 'Inherit from lineup'


class LineupVersionNoteForm(forms.ModelForm):
    class Meta:
        model = LineupVersionNote
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Add a note...'}),
        }


class DeckAddForm(forms.Form):
    deck_url = forms.CharField(
        required=True,
        label='Deck URL or ID',
        help_text='Paste a Master Vault or DoK link, or the deck UUID'
    )

    def clean_deck_url(self):
        value = self.cleaned_data['deck_url']
        deck_id = Deck.get_id_from_master_vault_url(value)
        return deck_id
