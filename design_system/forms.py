from django import forms

DECK_HOUSES = (
    ('brobnar', 'Brobnar'),
    ('dis', 'Dis'),
    ('logos', 'Logos'),
    ('mars', 'Mars'),
)

EVENT_FORMATS = (
    ('archon', 'Archon'),
    ('sealed', 'Sealed'),
    ('alliance', 'Alliance'),
)


class ComponentDemoForm(forms.Form):
    deck_name = forms.CharField(help_text='As it appears on the Master Vault.')
    contact_email = forms.EmailField(required=False)
    event_format = forms.ChoiceField(choices=EVENT_FORMATS)
    pairing = forms.ChoiceField(
        choices=(('swiss', 'Swiss'), ('single-elimination', 'Single elimination')),
        widget=forms.RadioSelect,
        initial='swiss',
    )
    houses = forms.MultipleChoiceField(choices=DECK_HOUSES, widget=forms.CheckboxSelectMultiple, required=False)
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
    is_public = forms.BooleanField(required=False, label='List this deck publicly', help_text='Anyone with the link can view it.')

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('event_format') == 'alliance' and len(cleaned_data.get('houses', [])) < 3:
            raise forms.ValidationError('Alliance decks need three houses.')
        return cleaned_data


class DialogDemoForm(forms.Form):
    deck_name = forms.CharField(help_text='Leave this empty and save to see errors re-render inside the dialog.')
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)


INVALID_DEMO_PREFIX = 'invalid'
INVALID_DEMO_DATA = {
    'deck_name': '',
    'contact_email': 'not-an-email',
    'event_format': 'alliance',
    'pairing': 'swiss',
    'houses': ['dis'],
}


def invalid_component_demo_form():
    form = ComponentDemoForm(
        data={f'{INVALID_DEMO_PREFIX}-{name}': value for name, value in INVALID_DEMO_DATA.items()},
        prefix=INVALID_DEMO_PREFIX,
    )
    form.is_valid()
    return form
