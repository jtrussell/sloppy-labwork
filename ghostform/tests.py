import csv
import io
import json
import uuid
from decimal import Decimal
from xml.etree import ElementTree

from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import FILTERABLE_CHOICE_COUNT, QuestionsPayloadForm
from .hooks import (
    get_response_form, has_linked_responses, mark_responses_context_removed,
    register_response_access_check, update_response_context
)
from .models import (
    Answer, Form, Question, Response, RESPONSE_ACCESS_CHECKS, MAXIMUM_QUESTIONS_PER_FORM
)


FAST_PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
SIMPLE_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

DECK_UUID = '2dea0ea6-e371-4b9a-826c-28f6620ef550'
MASTER_VAULT_DECK_LINK = f'https://www.keyforgegame.com/deck-details/{DECK_UUID}'
DOK_DECK_LINK = f'https://decksofkeyforge.com/decks/{DECK_UUID}'


class GhostformTestMixin:
    def _create_form(self, owner, title='Deck Survey', status=Form.Status.PUBLISHED):
        return Form.objects.create(owner=owner, title=title, status=status)

    def _add_question(self, ghostform, label, answer_type=Question.AnswerType.TEXT,
                      is_required=False, choices=None, order=None, allows_multiple_answers=False,
                      minimum_selections=None, maximum_selections=None):
        return Question.objects.create(
            form=ghostform,
            label=label,
            answer_type=answer_type,
            is_required=is_required,
            choices=choices or [],
            allows_multiple_answers=allows_multiple_answers,
            minimum_selections=minimum_selections,
            maximum_selections=maximum_selections,
            order=order or ghostform.questions.count() + 1,
        )

    def _builder_entry(self, label, answer_type=Question.AnswerType.TEXT, question_id=None,
                       is_required=False, choices=None, description='', allows_multiple_answers=False,
                       minimum_selections=None, maximum_selections=None):
        return {
            'id': question_id,
            'label': label,
            'description': description,
            'answer_type': answer_type,
            'is_required': is_required,
            'choices': choices or [],
            'allows_multiple_answers': allows_multiple_answers,
            'minimum_selections': minimum_selections,
            'maximum_selections': maximum_selections,
        }

    def _submit_response(self, ghostform, user, data):
        response_form = get_response_form(ghostform, data)
        self.assertTrue(response_form.is_valid(), response_form.errors)
        return ghostform.record_response(response_form, user)

    def _field_data(self, question, value):
        return {f'ghostform-{question.get_field_name()}': value}


class ResponseFormTestCase(GhostformTestMixin, TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.ghostform = self._create_form(self.owner)

    def _build_form(self, data=None, all_optional=False):
        return get_response_form(self.ghostform, data, all_optional=all_optional)

    def test_builds_one_field_per_active_question_in_order(self):
        second = self._add_question(self.ghostform, 'Second', order=2)
        first = self._add_question(self.ghostform, 'First', order=1)
        archived = self._add_question(self.ghostform, 'Archived', order=3)
        archived.archive()

        response_form = self._build_form()

        self.assertEqual(
            list(response_form.fields), [first.get_field_name(), second.get_field_name()])

    def test_field_uses_label_description_and_required_flag(self):
        question = self._add_question(self.ghostform, 'Your deck', is_required=True)
        question.description = 'Paste a link'
        question.save()

        field = self._build_form().fields[question.get_field_name()]

        self.assertEqual(field.label, 'Your deck')
        self.assertEqual(field.help_text, 'Paste a link')
        self.assertTrue(field.required)

    def test_all_optional_relaxes_required_questions(self):
        question = self._add_question(self.ghostform, 'Your deck', is_required=True)

        response_form = self._build_form({}, all_optional=True)

        self.assertFalse(response_form.fields[question.get_field_name()].required)
        self.assertTrue(response_form.is_valid())

    def test_required_text_question_rejects_blank_answer(self):
        question = self._add_question(self.ghostform, 'Name', is_required=True)

        response_form = self._build_form(self._field_data(question, '   '))

        self.assertFalse(response_form.is_valid())
        self.assertIn(question.get_field_name(), response_form.errors)

    def test_unchecked_required_checkbox_is_a_valid_answer(self):
        question = self._add_question(
            self.ghostform, 'First event?', answer_type=Question.AnswerType.CHECKBOX, is_required=True)

        response_form = self._build_form({})

        self.assertTrue(response_form.is_valid())
        self.assertEqual(response_form.get_answer_fields(), [
            {'question': question, 'value': 'No'}])

    def test_checked_checkbox_records_yes(self):
        question = self._add_question(
            self.ghostform, 'First event?', answer_type=Question.AnswerType.CHECKBOX)

        response_form = self._build_form(self._field_data(question, 'on'))

        self.assertTrue(response_form.is_valid())
        self.assertEqual(response_form.get_answer_fields()[0]['value'], 'Yes')

    def test_number_answers_are_normalized(self):
        question = self._add_question(
            self.ghostform, 'Chains', answer_type=Question.AnswerType.NUMBER)
        expected_values = {'1.50': '1.5', '100': '100', '0': '0', '-2.25': '-2.25'}

        for submitted_value, stored_value in expected_values.items():
            response_form = self._build_form(self._field_data(question, submitted_value))
            self.assertTrue(response_form.is_valid(), submitted_value)
            self.assertEqual(response_form.get_answer_fields()[0]['value'], stored_value)

    def test_number_question_rejects_text(self):
        question = self._add_question(
            self.ghostform, 'Chains', answer_type=Question.AnswerType.NUMBER)

        response_form = self._build_form(self._field_data(question, 'three'))

        self.assertFalse(response_form.is_valid())

    def test_number_question_rejects_oversized_values(self):
        question = self._add_question(
            self.ghostform, 'Chains', answer_type=Question.AnswerType.NUMBER)

        for oversized_value in ['1e1000000000', '1e999999', '1' * 21, '0.1234567']:
            response_form = self._build_form(self._field_data(question, oversized_value))
            self.assertFalse(response_form.is_valid(), oversized_value)

    def test_number_field_allows_decimals_in_the_browser(self):
        question = self._add_question(
            self.ghostform, 'Chains', answer_type=Question.AnswerType.NUMBER)

        rendered_field = str(self._build_form()[question.get_field_name()])

        self.assertIn('type="number"', rendered_field)
        self.assertIn('step="any"', rendered_field)

    def test_deck_link_accepts_master_vault_and_dok_links(self):
        question = self._add_question(
            self.ghostform, 'Deck', answer_type=Question.AnswerType.DECK_LINK)
        valid_links = [
            MASTER_VAULT_DECK_LINK,
            f'https://keyforgegame.com/deck-details/{DECK_UUID}',
            f'http://www.keyforgegame.com/deck-details/{DECK_UUID}?powerLevel=0',
            DOK_DECK_LINK,
            f'https://www.decksofkeyforge.com/decks/{DECK_UUID}/',
            f'https://decksofkeyforge.com/decks/{DECK_UUID.upper()}',
        ]

        for link in valid_links:
            response_form = self._build_form(self._field_data(question, link))
            self.assertTrue(response_form.is_valid(), link)
            answer_fields = response_form.get_answer_fields()[0]
            self.assertEqual(answer_fields['value'], link)
            self.assertEqual(answer_fields['deck_id'], DECK_UUID)

    def test_deck_link_rejects_other_links(self):
        question = self._add_question(
            self.ghostform, 'Deck', answer_type=Question.AnswerType.DECK_LINK)
        invalid_links = [
            f'https://example.com/deck-details/{DECK_UUID}',
            f'https://evil-keyforgegame.com/deck-details/{DECK_UUID}',
            'https://www.keyforgegame.com/deck-details/not-a-deck',
            f'https://decksofkeyforge.com/alliance-decks/{DECK_UUID}',
            DECK_UUID,
            f'https://www.keyforgegame.com/deck-details/{DECK_UUID}extra',
        ]

        for link in invalid_links:
            response_form = self._build_form(self._field_data(question, link))
            self.assertFalse(response_form.is_valid(), link)

    def test_deck_link_field_has_browser_pattern(self):
        question = self._add_question(
            self.ghostform, 'Deck', answer_type=Question.AnswerType.DECK_LINK)

        rendered_field = str(self._build_form()[question.get_field_name()])

        self.assertIn('pattern=', rendered_field)
        self.assertIn('type="url"', rendered_field)

    def test_multiple_choice_renders_select_with_blank_option(self):
        question = self._add_question(
            self.ghostform, 'House', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=['Brobnar', 'Dis'])

        field = self._build_form().fields[question.get_field_name()]
        rendered_field = str(self._build_form()[question.get_field_name()])

        self.assertEqual(field.choices, [('', 'Choose…'), ('Brobnar', 'Brobnar'), ('Dis', 'Dis')])
        self.assertIn('<select', rendered_field)

    def test_multiple_choice_rejects_unknown_option(self):
        question = self._add_question(
            self.ghostform, 'House', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=['Brobnar', 'Dis'])

        response_form = self._build_form(self._field_data(question, 'Logos'))

        self.assertFalse(response_form.is_valid())

    def test_required_multiple_choice_rejects_blank_option(self):
        question = self._add_question(
            self.ghostform, 'House', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=['Brobnar'], is_required=True)

        response_form = self._build_form(self._field_data(question, ''))

        self.assertFalse(response_form.is_valid())

    def test_multiple_answer_question_renders_checkboxes(self):
        question = self._add_question(
            self.ghostform, 'Houses', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=['Brobnar', 'Dis'], allows_multiple_answers=True)

        field = self._build_form().fields[question.get_field_name()]
        rendered_field = str(self._build_form()[question.get_field_name()])

        self.assertEqual(field.choices, [('Brobnar', 'Brobnar'), ('Dis', 'Dis')])
        self.assertEqual(rendered_field.count('type="checkbox"'), 2)

    def test_only_long_multiple_answer_lists_get_a_filter(self):
        short_question = self._add_question(
            self.ghostform, 'Houses', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=[f'House {number}' for number in range(FILTERABLE_CHOICE_COUNT)],
            allows_multiple_answers=True)
        long_question = self._add_question(
            self.ghostform, 'Cards', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=[f'Card {number}' for number in range(FILTERABLE_CHOICE_COUNT + 1)],
            allows_multiple_answers=True)
        response_form = self._build_form()

        short_field_html = render_to_string(
            'ghostform/partials/response-fields.html',
            {'response_form': [response_form[short_question.get_field_name()]]})
        long_field_html = render_to_string(
            'ghostform/partials/response-fields.html',
            {'response_form': [response_form[long_question.get_field_name()]]})

        self.assertNotIn('data-choice-filter', short_field_html)
        self.assertIn('data-choice-filter', long_field_html)
        self.assertIn('ghostform-choice-options--scrollable', long_field_html)
        self.assertEqual(long_field_html.count('type="checkbox"'), FILTERABLE_CHOICE_COUNT + 1)

    def test_multiple_answer_selection_limits_are_enforced(self):
        question = self._add_question(
            self.ghostform, 'Houses', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=['Brobnar', 'Dis', 'Logos', 'Mars'], allows_multiple_answers=True,
            minimum_selections=3, maximum_selections=3)
        cases = [
            ([], True),
            (['Brobnar', 'Dis'], False),
            (['Brobnar', 'Dis', 'Mars'], True),
            (['Brobnar', 'Dis', 'Logos', 'Mars'], False),
        ]

        for selections, expected in cases:
            response_form = self._build_form(self._field_data(question, selections))
            self.assertEqual(response_form.is_valid(), expected, selections)
            if not expected:
                self.assertEqual(
                    response_form.errors[question.get_field_name()], ['Choose exactly 3 options.'])

    def test_required_question_with_minimum_rejects_empty_selection(self):
        question = self._add_question(
            self.ghostform, 'Houses', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=['Brobnar', 'Dis'], is_required=True, allows_multiple_answers=True,
            minimum_selections=2)

        self.assertFalse(self._build_form({}).is_valid())
        self.assertTrue(self._build_form(self._field_data(question, ['Brobnar', 'Dis'])).is_valid())

    def test_selection_limits_and_count_are_rendered(self):
        question = self._add_question(
            self.ghostform, 'Houses', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=['Brobnar', 'Dis', 'Mars'], allows_multiple_answers=True,
            minimum_selections=2, maximum_selections=3)
        response_form = self._build_form(self._field_data(question, ['Dis']))

        field_html = render_to_string(
            'ghostform/partials/response-fields.html',
            {'response_form': [response_form[question.get_field_name()]]})

        self.assertIn('Choose between 2 and 3 options.', field_html)
        self.assertIn('data-maximum-selections="3"', field_html)
        self.assertIn('1 of 3 selected', field_html)

    def test_multiple_answer_selections_are_stored_one_per_line(self):
        question = self._add_question(
            self.ghostform, 'Houses', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=['Brobnar', 'Dis', 'Mars'], allows_multiple_answers=True)

        response = self._submit_response(
            self.ghostform, self.owner, self._field_data(question, ['Brobnar', 'Mars']))

        self.assertEqual(response.answers.get().value, 'Brobnar\nMars')

    def test_required_multiple_answer_question_needs_a_selection(self):
        question = self._add_question(
            self.ghostform, 'Houses', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=['Brobnar'], is_required=True, allows_multiple_answers=True)

        self.assertFalse(self._build_form({}).is_valid())
        self.assertTrue(self._build_form(self._field_data(question, ['Brobnar'])).is_valid())

    def test_empty_multiple_answer_selection_is_not_an_answer(self):
        self._add_question(
            self.ghostform, 'Houses', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=['Brobnar'], allows_multiple_answers=True)

        response_form = self._build_form({}, all_optional=True)

        self.assertTrue(response_form.is_valid())
        self.assertFalse(response_form.has_any_answer())
        self.assertEqual(response_form.get_answer_fields(), [])

    def test_blank_optional_answers_are_not_stored(self):
        text_question = self._add_question(self.ghostform, 'Notes')
        number_question = self._add_question(
            self.ghostform, 'Chains', answer_type=Question.AnswerType.NUMBER)

        response = self._submit_response(self.ghostform, self.owner, {
            **self._field_data(text_question, ''),
            **self._field_data(number_question, '3'),
        })

        self.assertEqual(
            list(response.answers.values_list('question_id', 'value')),
            [(number_question.id, '3')])

    def test_has_any_answer(self):
        number_question = self._add_question(
            self.ghostform, 'Chains', answer_type=Question.AnswerType.NUMBER)
        checkbox_question = self._add_question(
            self.ghostform, 'First event?', answer_type=Question.AnswerType.CHECKBOX)
        cases = [
            ({}, False),
            (self._field_data(number_question, '0'), True),
            (self._field_data(checkbox_question, 'on'), True),
        ]

        for data, expected in cases:
            response_form = self._build_form(data, all_optional=True)
            self.assertTrue(response_form.is_valid())
            self.assertEqual(response_form.has_any_answer(), expected, data)

    def test_record_response_stores_answers_and_context(self):
        deck_question = self._add_question(
            self.ghostform, 'Deck', answer_type=Question.AnswerType.DECK_LINK)
        response_form = get_response_form(
            self.ghostform, self._field_data(deck_question, MASTER_VAULT_DECK_LINK))
        self.assertTrue(response_form.is_valid())

        response = response_form.save_response(
            self.owner, context=[('Round', 2), ('Winner', 'Anvil')], context_key='match:1')

        self.assertEqual(response.context, [
            {'label': 'Round', 'value': 2}, {'label': 'Winner', 'value': 'Anvil'}])
        self.assertEqual(response.context_key, 'match:1')
        answer = response.answers.get()
        self.assertEqual(answer.deck_id, uuid.UUID(DECK_UUID))
        self.assertEqual(answer.value, MASTER_VAULT_DECK_LINK)

    def test_field_names_are_prefixed(self):
        question = self._add_question(self.ghostform, 'Name')

        rendered_field = str(self._build_form()[question.get_field_name()])

        self.assertIn(f'name="ghostform-{question.get_field_name()}"', rendered_field)


class SyncQuestionsTestCase(GhostformTestMixin, TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.ghostform = self._create_form(self.owner)

    def _answer(self, question, value='answer'):
        response = Response.objects.create(form=self.ghostform, user=self.owner)
        return Answer.objects.create(response=response, question=question, value=value)

    def test_creates_questions_in_submitted_order(self):
        self.ghostform.sync_questions([
            self._builder_entry('First', is_required=True, description='Context'),
            self._builder_entry('Second', Question.AnswerType.MULTIPLE_CHOICE, choices=['A', 'B']),
        ])

        questions = list(self.ghostform.get_active_questions())
        self.assertEqual([question.label for question in questions], ['First', 'Second'])
        self.assertEqual([question.order for question in questions], [1, 2])
        self.assertTrue(questions[0].is_required)
        self.assertEqual(questions[0].description, 'Context')
        self.assertEqual(questions[1].choices, ['A', 'B'])

    def test_reorders_existing_questions(self):
        first = self._add_question(self.ghostform, 'First')
        second = self._add_question(self.ghostform, 'Second')

        self.ghostform.sync_questions([
            self._builder_entry('Second', question_id=second.id),
            self._builder_entry('First', question_id=first.id),
        ])

        self.assertEqual(
            list(self.ghostform.get_active_questions().values_list('id', flat=True)),
            [second.id, first.id])

    def test_removed_question_without_answers_is_deleted(self):
        question = self._add_question(self.ghostform, 'Unused')

        self.ghostform.sync_questions([])

        self.assertFalse(Question.objects.filter(id=question.id).exists())

    def test_removed_question_with_answers_is_archived(self):
        question = self._add_question(self.ghostform, 'Answered')
        self._answer(question)

        self.ghostform.sync_questions([])

        question.refresh_from_db()
        self.assertTrue(question.is_archived)
        self.assertEqual(question.answers.count(), 1)

    def test_type_change_with_answers_archives_old_question(self):
        question = self._add_question(self.ghostform, 'Chains')
        self._answer(question, 'three')

        self.ghostform.sync_questions([
            self._builder_entry('Chains', Question.AnswerType.NUMBER, question_id=question.id),
        ])

        question.refresh_from_db()
        replacement = self.ghostform.get_active_questions().get()
        self.assertTrue(question.is_archived)
        self.assertNotEqual(replacement.id, question.id)
        self.assertEqual(replacement.answer_type, Question.AnswerType.NUMBER)

    def test_type_change_without_answers_updates_in_place(self):
        question = self._add_question(self.ghostform, 'Chains')

        self.ghostform.sync_questions([
            self._builder_entry('Chains', Question.AnswerType.NUMBER, question_id=question.id),
        ])

        question.refresh_from_db()
        self.assertFalse(question.is_archived)
        self.assertEqual(question.answer_type, Question.AnswerType.NUMBER)

    def test_label_edit_with_answers_keeps_question(self):
        question = self._add_question(self.ghostform, 'Deck')
        self._answer(question)

        self.ghostform.sync_questions([
            self._builder_entry('Your deck', question_id=question.id, is_required=True),
        ])

        question.refresh_from_db()
        self.assertFalse(question.is_archived)
        self.assertEqual(question.label, 'Your deck')
        self.assertTrue(question.is_required)

    def test_choices_are_cleared_for_non_choice_questions(self):
        self.ghostform.sync_questions([
            self._builder_entry('Notes', choices=['Leftover']),
        ])

        self.assertEqual(self.ghostform.get_active_questions().get().choices, [])

    def test_answer_mode_change_with_answers_keeps_question(self):
        question = self._add_question(
            self.ghostform, 'Houses', Question.AnswerType.MULTIPLE_CHOICE, choices=['Dis', 'Mars'])
        self._answer(question, 'Dis')

        self.ghostform.sync_questions([self._builder_entry(
            'Houses', Question.AnswerType.MULTIPLE_CHOICE, question_id=question.id,
            choices=['Dis', 'Mars'], allows_multiple_answers=True)])

        question.refresh_from_db()
        self.assertFalse(question.is_archived)
        self.assertTrue(question.allows_multiple_answers)

    def test_selection_limits_are_cleared_for_single_answer_questions(self):
        self.ghostform.sync_questions([self._builder_entry(
            'Houses', Question.AnswerType.MULTIPLE_CHOICE, choices=['Dis', 'Mars'],
            minimum_selections=1, maximum_selections=2)])

        question = self.ghostform.questions.get()
        self.assertIsNone(question.minimum_selections)
        self.assertIsNone(question.maximum_selections)

    def test_multiple_answers_are_cleared_for_non_choice_questions(self):
        self.ghostform.sync_questions([
            self._builder_entry('Notes', allows_multiple_answers=True),
        ])

        self.assertFalse(self.ghostform.questions.get().allows_multiple_answers)

    def test_ids_from_other_forms_create_new_questions(self):
        other_form = self._create_form(self.owner, title='Other')
        other_question = self._add_question(other_form, 'Not yours')

        self.ghostform.sync_questions([
            self._builder_entry('Mine', question_id=other_question.id),
        ])

        other_question.refresh_from_db()
        self.assertEqual(other_question.label, 'Not yours')
        self.assertEqual(other_question.form, other_form)
        self.assertEqual(self.ghostform.get_active_questions().get().label, 'Mine')

    def test_archived_questions_cannot_be_revived_by_id(self):
        question = self._add_question(self.ghostform, 'Old')
        self._answer(question)
        question.archive()

        self.ghostform.sync_questions([self._builder_entry('Old', question_id=question.id)])

        question.refresh_from_db()
        self.assertTrue(question.is_archived)
        self.assertEqual(self.ghostform.get_active_questions().count(), 1)

    def test_duplicate_copies_active_questions_without_responses(self):
        self.ghostform.description = 'Before each round'
        self.ghostform.save()
        first = self._add_question(self.ghostform, 'Deck', Question.AnswerType.DECK_LINK, is_required=True)
        archived = self._add_question(self.ghostform, 'Old')
        self._answer(archived)
        archived.archive()
        self._add_question(
            self.ghostform, 'House', Question.AnswerType.MULTIPLE_CHOICE, choices=['Dis', 'Logos'],
            allows_multiple_answers=True, minimum_selections=1, maximum_selections=2)
        self._answer(first)
        copier = User.objects.create_user('copier', 'copier@test.com', 'password')

        duplicated_form = self.ghostform.duplicate(owner=copier, title='Week 2 - Deck Survey')

        self.assertNotEqual(duplicated_form.code, self.ghostform.code)
        self.assertEqual(duplicated_form.owner, copier)
        self.assertEqual(duplicated_form.title, 'Week 2 - Deck Survey')
        self.assertEqual(duplicated_form.description, 'Before each round')
        self.assertEqual(duplicated_form.status, self.ghostform.status)
        self.assertFalse(duplicated_form.responses.exists())
        self.assertEqual(
            list(duplicated_form.questions.values_list(
                'label', 'answer_type', 'is_required', 'choices', 'allows_multiple_answers',
                'minimum_selections', 'maximum_selections', 'order')),
            [('Deck', 'deck_link', True, [], False, None, None, 1),
             ('House', 'multiple_choice', False, ['Dis', 'Logos'], True, 1, 2, 2)])
        self.assertEqual(self.ghostform.questions.count(), 3)

    def test_duplicate_truncates_long_titles(self):
        duplicated_form = self.ghostform.duplicate(owner=self.owner, title='x' * 250)

        self.assertEqual(len(duplicated_form.title), 200)

    def test_deleting_a_form_removes_answered_questions(self):
        question = self._add_question(self.ghostform, 'Answered')
        self._answer(question)

        self.ghostform.delete()

        self.assertFalse(Question.objects.exists())
        self.assertFalse(Answer.objects.exists())


class QuestionsPayloadFormTestCase(GhostformTestMixin, TestCase):
    def _clean(self, entries):
        payload = entries if isinstance(entries, str) else json.dumps(entries)
        form = QuestionsPayloadForm({'questions_payload': payload})
        form.is_valid()
        return form

    def test_valid_payload_is_normalized(self):
        form = self._clean([{
            'id': '7', 'label': '  Deck  ', 'description': ' Why ',
            'answer_type': 'multiple_choice', 'is_required': 1,
            'choices': [' Brobnar ', '', 'Dis'], 'allows_multiple_answers': 1,
            'minimum_selections': '', 'maximum_selections': ' 2 ',
        }])

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['questions_payload'], [{
            'id': 7, 'label': 'Deck', 'description': 'Why',
            'answer_type': 'multiple_choice', 'is_required': True,
            'choices': ['Brobnar', 'Dis'], 'allows_multiple_answers': True,
            'minimum_selections': None, 'maximum_selections': 2,
        }])

    def test_empty_question_list_is_valid(self):
        self.assertTrue(self._clean([]).is_valid())

    def test_rejects_unreadable_payload(self):
        self.assertFalse(self._clean('not json').is_valid())
        self.assertFalse(self._clean('{"label": "x"}').is_valid())
        self.assertFalse(self._clean(['not a question']).is_valid())

    def test_rejects_blank_label_and_unknown_type(self):
        form = self._clean([self._builder_entry('', answer_type='essay')])

        errors = form.errors['questions_payload']
        self.assertIn('Question 1: enter the question text.', errors)
        self.assertIn('Question 1: choose an answer type.', errors)

    def test_rejects_multiple_choice_without_options(self):
        form = self._clean([self._builder_entry('House', Question.AnswerType.MULTIPLE_CHOICE)])

        self.assertIn('Question 1: add at least one option.', form.errors['questions_payload'])

    def test_rejects_duplicate_options(self):
        form = self._clean([self._builder_entry(
            'House', Question.AnswerType.MULTIPLE_CHOICE, choices=['Dis', 'dis'])])

        self.assertIn('Question 1: options must be unique.', form.errors['questions_payload'])

    def test_rejects_options_with_semicolons_or_line_breaks(self):
        for choice in ['Dis; Mars', 'Dis\nMars']:
            form = self._clean([self._builder_entry(
                'House', Question.AnswerType.MULTIPLE_CHOICE, choices=[choice])])

            self.assertIn(
                "Question 1: options can't contain semicolons or line breaks.",
                form.errors['questions_payload'], choice)

    def test_rejects_invalid_selection_limits(self):
        cases = [
            ({'minimum_selections': 0}, 'selection limits must be whole numbers of 1 or more.'),
            ({'maximum_selections': 'three'}, 'selection limits must be whole numbers of 1 or more.'),
            ({'maximum_selections': 4}, "selection limits can't be more than the number of options."),
            ({'minimum_selections': 3, 'maximum_selections': 2}, "the minimum can't be more than the maximum."),
        ]

        for limits, expected_error in cases:
            form = self._clean([self._builder_entry(
                'House', Question.AnswerType.MULTIPLE_CHOICE, choices=['Dis', 'Logos', 'Mars'],
                allows_multiple_answers=True, **limits)])

            self.assertIn(f'Question 1: {expected_error}', form.errors['questions_payload'], limits)

    def test_selection_limits_are_ignored_for_single_answer_questions(self):
        form = self._clean([self._builder_entry(
            'House', Question.AnswerType.MULTIPLE_CHOICE, choices=['Dis'], maximum_selections=9)])

        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_too_many_questions(self):
        entries = [self._builder_entry(f'Q{i}') for i in range(MAXIMUM_QUESTIONS_PER_FORM + 1)]

        self.assertFalse(self._clean(entries).is_valid())

    def test_rejects_repeated_question_ids(self):
        form = self._clean([
            self._builder_entry('First', question_id=5),
            self._builder_entry('Second', question_id=5),
        ])

        self.assertIn('The question list could not be read.', form.errors['questions_payload'])

    def test_rejects_overlong_label(self):
        self.assertFalse(self._clean([self._builder_entry('x' * 201)]).is_valid())


class ResponseContextHooksTestCase(GhostformTestMixin, TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.ghostform = self._create_form(self.owner)
        self.response = Response.objects.create(
            form=self.ghostform, user=self.owner, context_key='match:1',
            context=[{'label': 'Winner', 'value': 'Anvil'}])

    def test_update_response_context_rewrites_active_responses(self):
        removed_response = Response.objects.create(
            form=self.ghostform, context_key='match:1', is_context_removed=True,
            context=[{'label': 'Winner', 'value': 'Old'}])

        update_response_context('match:1', [('Winner', 'Beacon')])

        self.response.refresh_from_db()
        removed_response.refresh_from_db()
        self.assertEqual(self.response.context, [{'label': 'Winner', 'value': 'Beacon'}])
        self.assertEqual(removed_response.context, [{'label': 'Winner', 'value': 'Old'}])

    def test_mark_responses_context_removed(self):
        mark_responses_context_removed('match:1')

        self.response.refresh_from_db()
        self.assertTrue(self.response.is_context_removed)
        self.assertFalse(has_linked_responses('match:1'))

    def test_has_linked_responses(self):
        self.assertTrue(has_linked_responses('match:1'))
        self.assertFalse(has_linked_responses('match:2'))


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class GhostformViewsTestCase(GhostformTestMixin, TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.stranger = User.objects.create_user('stranger', 'stranger@test.com', 'password')
        self.client.login(username='owner', password='password')

    def _url(self, name, ghostform=None):
        args = [ghostform.code] if ghostform else []
        return reverse(f'ghostform:{name}', args=args)

    def _builder_post_data(self, entries, title='Deck Survey', description=''):
        return {
            'title': title,
            'description': description,
            'questions_payload': json.dumps(entries),
        }

    def test_list_requires_login(self):
        self.client.logout()

        response = self.client.get(self._url('ghostform-list'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_list_shows_only_own_forms_with_stats(self):
        ghostform = self._create_form(self.owner)
        question = self._add_question(ghostform, 'Name')
        archived_question = self._add_question(ghostform, 'Old')
        archived_question.archive()
        self._submit_response(ghostform, self.owner, self._field_data(question, 'A'))
        self._submit_response(ghostform, self.stranger, self._field_data(question, 'B'))
        self._create_form(self.stranger, title='Not mine')

        response = self.client.get(self._url('ghostform-list'))

        listed_forms = list(response.context['forms_page'])
        self.assertEqual(listed_forms, [ghostform])
        self.assertEqual(listed_forms[0].response_count, 2)
        self.assertEqual(listed_forms[0].question_count, 1)
        self.assertIsNotNone(listed_forms[0].latest_response_on)
        self.assertNotContains(response, 'Not mine')
        self.assertContains(response, '2 responses')

    def test_list_is_paginated(self):
        for i in range(21):
            self._create_form(self.owner, title=f'Form {i}')

        first_page = self.client.get(self._url('ghostform-list'))
        second_page = self.client.get(self._url('ghostform-list') + '?page=2')

        self.assertEqual(len(first_page.context['forms_page']), 20)
        self.assertEqual(len(second_page.context['forms_page']), 1)
        self.assertContains(first_page, 'Page 1 of 2')

    def test_list_empty_state(self):
        response = self.client.get(self._url('ghostform-list'))

        self.assertContains(response, 'Create Your First Form')

    def test_create_form_with_questions(self):
        response = self.client.post(self._url('ghostform-create'), self._builder_post_data([
            self._builder_entry('Deck', Question.AnswerType.DECK_LINK, is_required=True),
            self._builder_entry('House', Question.AnswerType.MULTIPLE_CHOICE, choices=['Dis']),
        ]))

        ghostform = Form.objects.get()
        self.assertRedirects(response, self._url('ghostform-detail', ghostform))
        self.assertEqual(ghostform.owner, self.owner)
        self.assertEqual(ghostform.status, Form.Status.DRAFT)
        self.assertTrue(ghostform.code.startswith('gfm_'))
        self.assertEqual(
            list(ghostform.get_active_questions().values_list('label', flat=True)), ['Deck', 'House'])

    def test_create_form_with_invalid_questions_keeps_submitted_entries(self):
        entries = [self._builder_entry('', Question.AnswerType.TEXT)]

        response = self.client.post(self._url('ghostform-create'), self._builder_post_data(entries))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Form.objects.exists())
        self.assertEqual(response.context['builder_config']['questions'], entries)
        self.assertContains(response, 'Question 1: enter the question text.')

    def test_malformed_resubmitted_entries_are_dropped(self):
        response = self.client.post(self._url('ghostform-create'), {
            'title': 'Deck Survey', 'questions_payload': json.dumps([None, 'x', {'label': ''}]),
        })

        self.assertEqual(response.context['builder_config']['questions'], [{'label': ''}])

    def test_create_form_requires_title(self):
        response = self.client.post(self._url('ghostform-create'), self._builder_post_data([], title=''))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Form.objects.exists())

    def test_builder_offers_house_and_set_presets(self):
        from decks.models import House, Set
        House.objects.create(name='Brobnar', src='https://example.com/brobnar.png')
        Set.objects.create(id=999, name='Legal Set', src='https://example.com/set.png')
        Set.objects.create(id=998, name='Banned Set', src='https://example.com/set.png',
                           is_tournament_legal=False)

        response = self.client.get(self._url('ghostform-create'))

        presets = response.context['builder_config']['choice_presets']
        self.assertIn('Brobnar', presets['houses'])
        self.assertIn('Legal Set', presets['sets'])
        self.assertNotIn('Banned Set', presets['sets'])
        self.assertContains(response, 'id="ghostform-builder-config"')

    def test_edit_form_updates_questions(self):
        ghostform = self._create_form(self.owner)
        question = self._add_question(ghostform, 'Deck')

        self.client.post(self._url('ghostform-edit', ghostform), self._builder_post_data([
            self._builder_entry('Your deck', question_id=question.id),
        ], title='Renamed'))

        ghostform.refresh_from_db()
        question.refresh_from_db()
        self.assertEqual(ghostform.title, 'Renamed')
        self.assertEqual(question.label, 'Your deck')

    def test_edit_page_lists_existing_questions(self):
        ghostform = self._create_form(self.owner)
        question = self._add_question(ghostform, 'Deck')

        response = self.client.get(self._url('ghostform-edit', ghostform))

        self.assertEqual(response.context['builder_config']['questions'], [question.to_builder_entry()])

    def test_only_owner_can_edit(self):
        ghostform = self._create_form(self.stranger)

        get_response = self.client.get(self._url('ghostform-edit', ghostform))
        post_response = self.client.post(
            self._url('ghostform-edit', ghostform), self._builder_post_data([], title='Hijacked'))

        ghostform.refresh_from_db()
        self.assertEqual(get_response.status_code, 403)
        self.assertEqual(post_response.status_code, 403)
        self.assertEqual(ghostform.title, 'Deck Survey')

    def test_publish_requires_a_question(self):
        ghostform = self._create_form(self.owner, status=Form.Status.DRAFT)

        self.client.post(self._url('ghostform-update-status', ghostform), {'status': 'published'})

        ghostform.refresh_from_db()
        self.assertEqual(ghostform.status, Form.Status.DRAFT)

    def test_publish_and_close_form(self):
        ghostform = self._create_form(self.owner, status=Form.Status.DRAFT)
        self._add_question(ghostform, 'Deck')

        self.client.post(self._url('ghostform-update-status', ghostform), {'status': 'published'})
        ghostform.refresh_from_db()
        self.assertEqual(ghostform.status, Form.Status.PUBLISHED)

        self.client.post(self._url('ghostform-update-status', ghostform), {'status': 'closed'})
        ghostform.refresh_from_db()
        self.assertEqual(ghostform.status, Form.Status.CLOSED)

    def test_status_rejects_unknown_value_and_non_owner(self):
        ghostform = self._create_form(self.owner, status=Form.Status.DRAFT)
        self._add_question(ghostform, 'Deck')

        self.client.post(self._url('ghostform-update-status', ghostform), {'status': 'archived'})
        self.client.login(username='stranger', password='password')
        stranger_response = self.client.post(
            self._url('ghostform-update-status', ghostform), {'status': 'published'})

        ghostform.refresh_from_db()
        self.assertEqual(ghostform.status, Form.Status.DRAFT)
        self.assertEqual(stranger_response.status_code, 403)

    def test_detail_for_owner(self):
        ghostform = self._create_form(self.owner)
        self._add_question(ghostform, 'Deck')

        response = self.client.get(self._url('ghostform-detail', ghostform))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_edit'])
        self.assertContains(response, self._url('ghostform-fill', ghostform))
        self.assertContains(response, self._url('ghostform-responses-csv', ghostform))

    def test_draft_preview_link_hidden_from_read_only_viewers(self):
        ghostform = self._create_form(self.owner, status=Form.Status.DRAFT)

        def allow_stranger(user, checked_form):
            return user.username == 'stranger'

        register_response_access_check(allow_stranger)
        self.addCleanup(RESPONSE_ACCESS_CHECKS.remove, allow_stranger)
        owner_response = self.client.get(self._url('ghostform-detail', ghostform))
        self.client.login(username='stranger', password='password')
        stranger_response = self.client.get(self._url('ghostform-detail', ghostform))

        self.assertContains(owner_response, '>Preview</a>')
        self.assertNotContains(stranger_response, '>Preview</a>')

    def test_detail_forbidden_for_stranger(self):
        ghostform = self._create_form(self.owner)
        self.client.login(username='stranger', password='password')

        response = self.client.get(self._url('ghostform-detail', ghostform))

        self.assertEqual(response.status_code, 403)

    def test_registered_access_check_grants_read_only_access(self):
        ghostform = self._create_form(self.owner)

        def allow_stranger(user, checked_form):
            return user.username == 'stranger' and checked_form == ghostform

        register_response_access_check(allow_stranger)
        self.addCleanup(RESPONSE_ACCESS_CHECKS.remove, allow_stranger)
        self.client.login(username='stranger', password='password')

        detail_response = self.client.get(self._url('ghostform-detail', ghostform))
        csv_response = self.client.get(self._url('ghostform-responses-csv', ghostform))
        edit_response = self.client.get(self._url('ghostform-edit', ghostform))

        self.assertEqual(detail_response.status_code, 200)
        self.assertFalse(detail_response.context['can_edit'])
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(edit_response.status_code, 403)

    def test_fill_requires_login(self):
        ghostform = self._create_form(self.owner)
        self.client.logout()

        response = self.client.get(self._url('ghostform-fill', ghostform))

        self.assertEqual(response.status_code, 302)

    def test_fill_records_response(self):
        ghostform = self._create_form(self.owner)
        question = self._add_question(ghostform, 'Deck', is_required=True)
        self.client.login(username='stranger', password='password')

        response = self.client.post(
            self._url('ghostform-fill', ghostform), self._field_data(question, 'My deck'))

        self.assertRedirects(response, self._url('ghostform-fill-thanks', ghostform))
        saved_response = ghostform.responses.get()
        self.assertEqual(saved_response.user, self.stranger)
        self.assertEqual(saved_response.context, [])
        self.assertEqual(saved_response.answers.get().value, 'My deck')

    def test_fill_allows_multiple_submissions(self):
        ghostform = self._create_form(self.owner)
        question = self._add_question(ghostform, 'Deck')

        for value in ['One', 'Two']:
            self.client.post(self._url('ghostform-fill', ghostform), self._field_data(question, value))

        self.assertEqual(ghostform.responses.count(), 2)

    def test_fill_with_invalid_answers_shows_errors(self):
        ghostform = self._create_form(self.owner)
        question = self._add_question(
            ghostform, 'Deck', answer_type=Question.AnswerType.DECK_LINK, is_required=True)

        response = self.client.post(
            self._url('ghostform-fill', ghostform), self._field_data(question, 'nope'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ghostform.responses.exists())
        self.assertContains(response, 'Enter a Master Vault or Decks of KeyForge deck link.')

    def test_draft_form_is_hidden_from_others_and_previewable_by_owner(self):
        ghostform = self._create_form(self.owner, status=Form.Status.DRAFT)
        question = self._add_question(ghostform, 'Deck')

        owner_response = self.client.get(self._url('ghostform-fill', ghostform))
        self.client.post(self._url('ghostform-fill', ghostform), self._field_data(question, 'x'))
        self.client.login(username='stranger', password='password')
        stranger_response = self.client.get(self._url('ghostform-fill', ghostform))

        self.assertEqual(owner_response.status_code, 200)
        self.assertTrue(owner_response.context['is_preview'])
        self.assertFalse(ghostform.responses.exists())
        self.assertEqual(stranger_response.status_code, 404)

    def test_closed_form_does_not_accept_responses(self):
        ghostform = self._create_form(self.owner, status=Form.Status.CLOSED)
        question = self._add_question(ghostform, 'Deck')
        self.client.login(username='stranger', password='password')

        get_response = self.client.get(self._url('ghostform-fill', ghostform))
        self.client.post(self._url('ghostform-fill', ghostform), self._field_data(question, 'x'))

        self.assertContains(get_response, 'no longer accepting responses')
        self.assertNotContains(get_response, 'type="submit"')
        self.assertFalse(ghostform.responses.exists())

    def test_thanks_page(self):
        ghostform = self._create_form(self.owner)

        response = self.client.get(self._url('ghostform-fill-thanks', ghostform))

        self.assertContains(response, 'Your response has been recorded')

    def test_description_and_help_text_are_escaped(self):
        ghostform = self._create_form(self.owner)
        ghostform.description = '<script>alert(1)</script>'
        ghostform.save()
        question = self._add_question(ghostform, '<b>Deck</b>')
        question.description = '<img src=x onerror=alert(1)>'
        question.save()

        response = self.client.get(self._url('ghostform-fill', ghostform))

        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertNotContains(response, '<img src=x')
        self.assertNotContains(response, '<b>Deck</b>')

    def test_picker_results_list_own_forms_by_recent_edit(self):
        older = self._create_form(self.owner, title='Deck Survey Old')
        newer = self._create_form(self.owner, title='Deck Survey New')
        self._add_question(newer, 'Deck')
        Form.objects.filter(pk=older.pk).update(updated_on=newer.updated_on.replace(year=2020))
        self._create_form(self.stranger, title='Deck Survey Theirs')

        response = self.client.get(self._url('ghostform-picker-results'))

        self.assertEqual(
            [option['title'] for option in response.context['results']],
            ['Deck Survey New', 'Deck Survey Old'])
        self.assertIn('Published · 1 question · 0 responses · not linked · edited',
                      response.context['results'][0]['meta'])
        self.assertContains(response, 'Recently edited')

    def test_picker_results_filter_by_query(self):
        self._create_form(self.owner, title='Deck Survey')
        self._create_form(self.owner, title='Feedback')

        response = self.client.get(self._url('ghostform-picker-results'), {'q': 'feed'})

        self.assertEqual([option['title'] for option in response.context['results']], ['Feedback'])
        self.assertContains(response, 'Matching forms')

    def test_picker_results_empty_search(self):
        response = self.client.get(self._url('ghostform-picker-results'), {'q': 'zzz'})

        self.assertContains(response, 'No forms match')

    def test_picker_results_are_limited(self):
        for i in range(25):
            self._create_form(self.owner, title=f'Form {i}')

        response = self.client.get(self._url('ghostform-picker-results'))

        self.assertEqual(len(response.context['results']), 20)

    def test_picker_preview_lists_questions_for_viewers_only(self):
        ghostform = self._create_form(self.owner)
        self._add_question(ghostform, 'Your deck', Question.AnswerType.DECK_LINK, is_required=True)

        owner_response = self.client.get(self._url('ghostform-picker-preview', ghostform))
        self.client.login(username='stranger', password='password')
        stranger_response = self.client.get(self._url('ghostform-picker-preview', ghostform))

        self.assertContains(owner_response, 'Your deck')
        self.assertContains(owner_response, 'Deck link')
        self.assertEqual(stranger_response.status_code, 403)

    def test_gizmo_list_links_to_ghostform(self):
        response = self.client.get(reverse('redacted-list'))

        self.assertContains(response, self._url('ghostform-list'))
        self.assertContains(response, 'Ghostform')


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class ResponsesCsvTestCase(GhostformTestMixin, TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.player = User.objects.create_user('player', 'player@test.com', 'password')
        self.client.login(username='owner', password='password')
        self.ghostform = self._create_form(self.owner, title='Deck Survey!')
        self.deck_question = self._add_question(
            self.ghostform, 'Deck', answer_type=Question.AnswerType.DECK_LINK)
        self.notes_question = self._add_question(self.ghostform, 'Notes')

    def _download_rows(self):
        response = self.client.get(
            reverse('ghostform:ghostform-responses-csv', args=[self.ghostform.code]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        return response, list(csv.reader(io.StringIO(response.content.decode())))

    def test_csv_has_header_and_one_row_per_response(self):
        self._submit_response(self.ghostform, self.player, {
            **self._field_data(self.deck_question, DOK_DECK_LINK),
            **self._field_data(self.notes_question, 'Good games'),
        })

        response, rows = self._download_rows()

        self.assertIn('deck-survey-responses.csv', response['Content-Disposition'])
        self.assertEqual(rows[0], ['Submitted at', 'User', 'Deck', 'Deck (Deck ID)', 'Notes'])
        self.assertEqual(rows[1][1:], ['player', DOK_DECK_LINK, DECK_UUID, 'Good games'])
        self.assertEqual(len(rows), 2)

    def test_context_columns_follow_first_seen_order(self):
        first = self._submit_response(self.ghostform, self.player, {})
        first.context = [{'label': 'Stage', 'value': 'Main'}, {'label': 'Round', 'value': 1}]
        first.context_key = 'match:1'
        first.save()
        second = self._submit_response(self.ghostform, self.player, {})
        second.context = [{'label': 'Stage', 'value': 'Playoffs'}, {'label': 'Pod', 'value': 'A'}]
        second.context_key = 'match:2'
        second.is_context_removed = True
        second.save()

        _response, rows = self._download_rows()

        self.assertEqual(rows[0][:6], [
            'Submitted at', 'User', 'Stage', 'Round', 'Pod', 'Linked record removed'])
        self.assertEqual(rows[1][2:6], ['Main', '1', '', ''])
        self.assertEqual(rows[2][2:6], ['Playoffs', '', 'A', 'Yes'])

    def test_archived_questions_are_listed_last(self):
        self._submit_response(self.ghostform, self.player, self._field_data(self.notes_question, 'Old note'))
        self.ghostform.sync_questions([
            self._builder_entry('Deck', Question.AnswerType.DECK_LINK, question_id=self.deck_question.id),
        ])

        _response, rows = self._download_rows()

        self.assertEqual(rows[0], [
            'Submitted at', 'User', 'Deck', 'Deck (Deck ID)', 'Notes (archived)'])
        self.assertEqual(rows[1][-1], 'Old note')

    def test_formula_like_answers_are_neutralized(self):
        self._submit_response(self.ghostform, self.player, self._field_data(
            self.notes_question, '=HYPERLINK("http://evil")'))
        number_question = self._add_question(
            self.ghostform, 'Score', answer_type=Question.AnswerType.NUMBER)
        self._submit_response(self.ghostform, self.player, self._field_data(number_question, '-3'))

        _response, rows = self._download_rows()

        self.assertEqual(rows[1][4], '\'=HYPERLINK("http://evil")')
        self.assertEqual(rows[2][5], '-3')

    def test_multiple_answer_selections_are_semicolon_delimited(self):
        houses_question = self._add_question(
            self.ghostform, 'Houses', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=['Brobnar', 'Dis', 'Mars'], allows_multiple_answers=True)
        self._submit_response(
            self.ghostform, self.player, self._field_data(houses_question, ['Brobnar', 'Mars']))

        _response, rows = self._download_rows()

        self.assertEqual(rows[1][-1], 'Brobnar;Mars')

    def test_csv_forbidden_for_stranger(self):
        self.client.login(username='player', password='password')

        response = self.client.get(
            reverse('ghostform:ghostform-responses-csv', args=[self.ghostform.code]))

        self.assertEqual(response.status_code, 403)

    def test_csv_answers_recorded_in_decimal_form(self):
        number_question = self._add_question(
            self.ghostform, 'Chains', answer_type=Question.AnswerType.NUMBER)
        self._submit_response(self.ghostform, self.player, self._field_data(number_question, '2.50'))

        _response, rows = self._download_rows()

        self.assertEqual(Decimal(rows[1][-1]), Decimal('2.5'))


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class ResponsesFeedTestCase(GhostformTestMixin, TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@test.com', 'password')
        self.player = User.objects.create_user('player', 'player@test.com', 'password')
        self.ghostform = self._create_form(self.owner)
        self.deck_question = self._add_question(
            self.ghostform, 'Deck', answer_type=Question.AnswerType.DECK_LINK)
        self.houses_question = self._add_question(
            self.ghostform, 'Houses', answer_type=Question.AnswerType.MULTIPLE_CHOICE,
            choices=['Brobnar', 'Dis', 'Mars'], allows_multiple_answers=True)
        self.notes_question = self._add_question(self.ghostform, 'Notes')
        response = self._submit_response(self.ghostform, self.player, {
            **self._field_data(self.deck_question, DOK_DECK_LINK),
            **self._field_data(self.houses_question, ['Brobnar', 'Mars']),
        })
        response.context = [{'label': 'Round', 'value': 1}]
        response.save()
        self.ghostform.rotate_feed_token()

    def _feed_url(self, feed_format, feed_token=None):
        return reverse(
            f'ghostform:ghostform-responses-feed-{feed_format}',
            args=[feed_token or self.ghostform.feed_token])

    def _update_feed(self, action):
        return self.client.post(
            reverse('ghostform:ghostform-update-feed', args=[self.ghostform.code]),
            {'action': action})

    def test_new_forms_have_no_feed_token(self):
        self.assertIsNone(self._create_form(self.owner).feed_token)

    def test_json_feed_is_public_and_lists_responses(self):
        response = self.client.get(self._feed_url('json'))

        self.assertEqual(response.status_code, 200)
        feed = response.json()
        self.assertEqual(feed['code'], self.ghostform.code)
        self.assertEqual(len(feed['responses']), 1)
        feed_response = feed['responses'][0]
        self.assertEqual(feed_response['user'], 'player')
        self.assertEqual(feed_response['context'], [{'label': 'Round', 'value': 1}])
        self.assertEqual(feed_response['answers'], [
            {'question': 'Deck', 'is_archived': False, 'value': DOK_DECK_LINK, 'deck_id': DECK_UUID},
            {'question': 'Houses', 'is_archived': False, 'value': 'Brobnar;Mars', 'deck_id': ''},
            {'question': 'Notes', 'is_archived': False, 'value': '', 'deck_id': ''},
        ])

    def test_xml_feed_is_public_and_lists_responses(self):
        response = self.client.get(self._feed_url('xml'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml')
        root = ElementTree.fromstring(response.content)
        self.assertEqual(root.findtext('code'), self.ghostform.code)
        self.assertEqual(root.findtext('responses/response/user'), 'player')
        self.assertEqual(root.findtext('responses/response/context/item/value'), '1')
        answers = root.findall('responses/response/answers/answer')
        self.assertEqual([answer.findtext('question') for answer in answers], ['Deck', 'Houses', 'Notes'])
        self.assertEqual(answers[0].findtext('deck_id'), DECK_UUID)
        self.assertEqual(answers[1].findtext('value'), 'Brobnar;Mars')

    def test_csv_feed_is_public_and_matches_export_columns(self):
        response = self.client.get(self._feed_url('csv'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertNotIn('Content-Disposition', response)
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0], [
            'Submitted at', 'User', 'Round', 'Deck', 'Deck (Deck ID)', 'Houses', 'Notes'])
        self.assertEqual(rows[1][1:], ['player', '1', DOK_DECK_LINK, DECK_UUID, 'Brobnar;Mars', ''])
        self.assertEqual(len(rows), 2)

    def test_unknown_feed_token_is_not_found(self):
        response = self.client.get(self._feed_url('json', uuid.uuid4()))

        self.assertEqual(response.status_code, 404)

    def test_owner_can_rotate_feed_token(self):
        original_token = self.ghostform.feed_token
        self.client.login(username='owner', password='password')

        response = self._update_feed('rotate')

        self.assertRedirects(response, reverse('ghostform:ghostform-detail', args=[self.ghostform.code]))
        self.ghostform.refresh_from_db()
        self.assertNotEqual(self.ghostform.feed_token, original_token)
        self.assertEqual(self.client.get(self._feed_url('json', original_token)).status_code, 404)
        self.assertEqual(self.client.get(self._feed_url('json')).status_code, 200)

    def test_owner_can_disable_feed(self):
        original_token = self.ghostform.feed_token
        self.client.login(username='owner', password='password')

        self._update_feed('disable')

        self.ghostform.refresh_from_db()
        self.assertIsNone(self.ghostform.feed_token)
        self.assertEqual(self.client.get(self._feed_url('xml', original_token)).status_code, 404)

    def test_stranger_cannot_update_feed(self):
        original_token = self.ghostform.feed_token
        self.client.login(username='player', password='password')

        response = self._update_feed('disable')

        self.assertEqual(response.status_code, 403)
        self.ghostform.refresh_from_db()
        self.assertEqual(self.ghostform.feed_token, original_token)

    def test_detail_shows_feed_links_to_owner(self):
        self.client.login(username='owner', password='password')

        response = self.client.get(reverse('ghostform:ghostform-detail', args=[self.ghostform.code]))

        self.assertContains(response, self._feed_url('csv'))
        self.assertContains(response, self._feed_url('xml'))
        self.assertContains(response, self._feed_url('json'))
