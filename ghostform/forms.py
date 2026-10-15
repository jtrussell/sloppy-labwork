import json
import re

from django import forms
from django.core.exceptions import ValidationError

from decks.models import Deck
from .models import (
    Form, Question, MAXIMUM_QUESTIONS_PER_FORM, MAXIMUM_CHOICES_PER_QUESTION,
    QUESTION_LABEL_MAX_LENGTH, QUESTION_DESCRIPTION_MAX_LENGTH, CHOICE_MAX_LENGTH,
    TEXT_ANSWER_MAX_LENGTH, ANSWER_SELECTION_SEPARATOR, CSV_SELECTION_DELIMITER,
    describe_selection_limits
)


UUID_PATTERN = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
DECK_LINK_PATTERN = (
    r'https?://(www\.)?(keyforgegame\.com/deck-details|decksofkeyforge\.com/decks)/'
    + UUID_PATTERN + r'([\/?#].*)?'
)
DECK_LINK_ERROR_MESSAGE = 'Enter a Master Vault or Decks of KeyForge deck link.'
NUMBER_ANSWER_MAX_DIGITS = 20
NUMBER_ANSWER_DECIMAL_PLACES = 6
FILTERABLE_CHOICE_COUNT = 12
INVALID_SELECTION_LIMIT = 0
FORBIDDEN_CHOICE_CHARACTERS = (CSV_SELECTION_DELIMITER, ANSWER_SELECTION_SEPARATOR, '\r')


class DeckLinkField(forms.CharField):
    widget = forms.URLInput

    def __init__(self, **kwargs):
        super().__init__(max_length=TEXT_ANSWER_MAX_LENGTH, **kwargs)

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        attrs.update({
            'pattern': DECK_LINK_PATTERN,
            'title': DECK_LINK_ERROR_MESSAGE,
            'placeholder': 'https://www.keyforgegame.com/deck-details/...',
        })
        return attrs

    def clean(self, value):
        deck_link = super().clean(value)
        if not deck_link:
            return None
        if not re.fullmatch(DECK_LINK_PATTERN, deck_link, flags=re.IGNORECASE):
            raise ValidationError(DECK_LINK_ERROR_MESSAGE)
        return {
            'url': deck_link,
            'deck_id': Deck.get_id_from_master_vault_url(deck_link).lower(),
        }


class MultipleAnswerField(forms.MultipleChoiceField):
    widget = forms.CheckboxSelectMultiple

    def __init__(self, *, minimum_selections=None, maximum_selections=None, **kwargs):
        super().__init__(**kwargs)
        self.minimum_selections = minimum_selections
        self.maximum_selections = maximum_selections

    @property
    def has_many_choices(self):
        return len(self.choices) > FILTERABLE_CHOICE_COUNT

    @property
    def selection_limits_description(self):
        return describe_selection_limits(self.minimum_selections, self.maximum_selections)

    def validate(self, value):
        super().validate(value)
        if value and not self._is_within_selection_limits(len(value)):
            raise ValidationError(self.selection_limits_description)

    def _is_within_selection_limits(self, selection_count):
        is_above_minimum = not self.minimum_selections or selection_count >= self.minimum_selections
        is_below_maximum = not self.maximum_selections or selection_count <= self.maximum_selections
        return is_above_minimum and is_below_maximum


def build_question_field(question, is_required):
    common_options = {
        'label': question.label,
        'help_text': question.description,
        'required': is_required,
    }
    answer_type = question.answer_type
    if answer_type == Question.AnswerType.NUMBER:
        return forms.DecimalField(
            max_digits=NUMBER_ANSWER_MAX_DIGITS,
            decimal_places=NUMBER_ANSWER_DECIMAL_PLACES,
            widget=forms.NumberInput(attrs={'step': 'any'}),
            **common_options)
    if answer_type == Question.AnswerType.DECK_LINK:
        return DeckLinkField(**common_options)
    if answer_type == Question.AnswerType.MULTIPLE_CHOICE and question.allows_multiple_answers:
        return MultipleAnswerField(
            choices=[(choice, choice) for choice in question.choices],
            minimum_selections=question.minimum_selections,
            maximum_selections=question.maximum_selections,
            **common_options)
    if answer_type == Question.AnswerType.MULTIPLE_CHOICE:
        choices = [('', 'Choose…')] + [(choice, choice)
                                       for choice in question.choices]
        return forms.ChoiceField(choices=choices, **common_options)
    if answer_type == Question.AnswerType.CHECKBOX:
        return forms.BooleanField(**{**common_options, 'required': False})
    return forms.CharField(max_length=TEXT_ANSWER_MAX_LENGTH, **common_options)


class ResponseForm(forms.Form):
    def __init__(self, *args, ghostform, questions=None, all_optional=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.ghostform = ghostform
        self.questions = list(
            ghostform.get_active_questions() if questions is None else questions)
        for question in self.questions:
            is_required = question.is_required and not all_optional
            self.fields[question.get_field_name()] = build_question_field(
                question, is_required)

    def save_response(self, user, context=(), context_key=''):
        return self.ghostform.record_response(self, user, context, context_key)

    def get_answer_fields(self):
        answer_fields = []
        for question in self.questions:
            fields = question.get_answer_fields(
                self.cleaned_data.get(question.get_field_name()))
            if fields is not None:
                answer_fields.append({'question': question, **fields})
        return answer_fields

    def has_any_answer(self):
        for question in self.questions:
            cleaned_value = self.cleaned_data.get(question.get_field_name())
            if cleaned_value is None or cleaned_value == '' or cleaned_value is False or cleaned_value == []:
                continue
            return True
        return False

    def get_error_summary(self):
        return '; '.join(
            f'{self.fields[field_name].label}: {" ".join(errors)}'
            for field_name, errors in self.errors.items()
            if field_name in self.fields
        )


class FormDetailsForm(forms.ModelForm):
    class Meta:
        model = Form
        fields = ['title', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class QuestionsPayloadForm(forms.Form):
    questions_payload = forms.CharField(widget=forms.HiddenInput)

    def clean_questions_payload(self):
        try:
            raw_entries = json.loads(self.cleaned_data['questions_payload'])
        except (TypeError, ValueError):
            raise ValidationError('The question list could not be read.')

        if not isinstance(raw_entries, list):
            raise ValidationError('The question list could not be read.')
        if len(raw_entries) > MAXIMUM_QUESTIONS_PER_FORM:
            raise ValidationError(
                f'A form can have at most {MAXIMUM_QUESTIONS_PER_FORM} questions.')

        question_entries = []
        errors = []
        for position, raw_entry in enumerate(raw_entries, start=1):
            entry, entry_errors = self._clean_question_entry(raw_entry)
            errors.extend(f'Question {position}: {error}' for error in entry_errors)
            question_entries.append(entry)

        submitted_question_ids = [
            entry['id'] for entry in question_entries if entry and entry['id'] is not None]
        if len(submitted_question_ids) != len(set(submitted_question_ids)):
            errors.append('The question list could not be read.')

        if errors:
            raise ValidationError(errors)
        return question_entries

    def _clean_question_entry(self, raw_entry):
        if not isinstance(raw_entry, dict):
            return None, ['could not be read.']

        entry = {
            'id': self._parse_question_id(raw_entry.get('id')),
            'label': str(raw_entry.get('label') or '').strip(),
            'description': str(raw_entry.get('description') or '').strip(),
            'answer_type': raw_entry.get('answer_type'),
            'is_required': bool(raw_entry.get('is_required')),
            'choices': self._parse_choices(raw_entry.get('choices')),
            'allows_multiple_answers': bool(raw_entry.get('allows_multiple_answers')),
            'minimum_selections': self._parse_selection_limit(raw_entry.get('minimum_selections')),
            'maximum_selections': self._parse_selection_limit(raw_entry.get('maximum_selections')),
        }

        errors = []
        if not entry['label']:
            errors.append('enter the question text.')
        elif len(entry['label']) > QUESTION_LABEL_MAX_LENGTH:
            errors.append(
                f'question text must be {QUESTION_LABEL_MAX_LENGTH} characters or fewer.')
        if len(entry['description']) > QUESTION_DESCRIPTION_MAX_LENGTH:
            errors.append(
                f'description must be {QUESTION_DESCRIPTION_MAX_LENGTH} characters or fewer.')
        if entry['answer_type'] not in Question.AnswerType.values:
            errors.append('choose an answer type.')
        if entry['answer_type'] == Question.AnswerType.MULTIPLE_CHOICE:
            errors.extend(self._get_choice_errors(entry['choices']))
            if entry['allows_multiple_answers']:
                errors.extend(self._get_selection_limit_errors(entry))
        return entry, errors

    @staticmethod
    def _parse_question_id(question_id):
        try:
            return int(question_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_selection_limit(raw_limit):
        if raw_limit is None or str(raw_limit).strip() == '':
            return None
        try:
            return int(str(raw_limit).strip())
        except ValueError:
            return INVALID_SELECTION_LIMIT

    @staticmethod
    def _get_selection_limit_errors(entry):
        selection_limits = [
            limit for limit in (entry['minimum_selections'], entry['maximum_selections']) if limit is not None]
        if any(limit < 1 for limit in selection_limits):
            return ['selection limits must be whole numbers of 1 or more.']
        errors = []
        if any(limit > len(entry['choices']) for limit in selection_limits):
            errors.append("selection limits can't be more than the number of options.")
        if len(selection_limits) == 2 and entry['minimum_selections'] > entry['maximum_selections']:
            errors.append("the minimum can't be more than the maximum.")
        return errors

    @staticmethod
    def _parse_choices(raw_choices):
        if not isinstance(raw_choices, list):
            return []
        stripped_choices = (str(choice).strip() for choice in raw_choices)
        return [choice for choice in stripped_choices if choice]

    @staticmethod
    def _get_choice_errors(choices):
        errors = []
        if not choices:
            errors.append('add at least one option.')
        if len(choices) > MAXIMUM_CHOICES_PER_QUESTION:
            errors.append(
                f'a question can have at most {MAXIMUM_CHOICES_PER_QUESTION} options.')
        if any(len(choice) > CHOICE_MAX_LENGTH for choice in choices):
            errors.append(
                f'options must be {CHOICE_MAX_LENGTH} characters or fewer.')
        if any(character in choice for choice in choices for character in FORBIDDEN_CHOICE_CHARACTERS):
            errors.append('options can\'t contain semicolons or line breaks.')
        folded_choices = [choice.casefold() for choice in choices]
        if len(folded_choices) != len(set(folded_choices)):
            errors.append('options must be unique.')
        return errors
