from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _


MAXIMUM_QUESTIONS_PER_FORM = 50
MAXIMUM_CHOICES_PER_QUESTION = 200
QUESTION_LABEL_MAX_LENGTH = 200
QUESTION_DESCRIPTION_MAX_LENGTH = 1000
CHOICE_MAX_LENGTH = 200
TEXT_ANSWER_MAX_LENGTH = 1000
ANSWER_SELECTION_SEPARATOR = '\n'
CSV_SELECTION_DELIMITER = ';'

RESPONSE_ACCESS_CHECKS = []
FORM_USAGE_DESCRIBERS = []


def generate_form_code():
    length = 6
    while True:
        code = 'gfm_' + get_random_string(
            length, allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        if not Form.objects.filter(code=code).exists():
            return code


class Form(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PUBLISHED = 'published', _('Published')
        CLOSED = 'closed', _('Closed')

    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='ghostforms')
    code = models.CharField(max_length=10, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(default='', blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_on']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generate_form_code()
        super().save(*args, **kwargs)

    def can_edit(self, user):
        return user.is_authenticated and self.owner_id == user.id

    def can_view_responses(self, user):
        if self.can_edit(user):
            return True
        if not user.is_authenticated:
            return False
        return any(check(user, self) for check in RESPONSE_ACCESS_CHECKS)

    def is_accepting_responses(self):
        return self.status == self.Status.PUBLISHED

    def get_active_questions(self):
        return self.questions.filter(is_archived=False)

    def get_questions_for_export(self):
        return sorted(self.questions.all(), key=lambda question: (question.is_archived, question.order, question.id))

    def sync_questions(self, question_entries):
        questions_by_id = {
            question.id: question for question in self.get_active_questions()}
        kept_question_ids = set()

        for order, entry in enumerate(question_entries, start=1):
            question = questions_by_id.get(entry['id'])
            if question and question.answer_type != entry['answer_type'] and question.answers.exists():
                question.archive()
                question = None

            if question is None:
                question = Question(form=self)
            else:
                kept_question_ids.add(question.id)

            question.label = entry['label']
            question.description = entry['description']
            is_multiple_choice = entry['answer_type'] == Question.AnswerType.MULTIPLE_CHOICE
            question.answer_type = entry['answer_type']
            question.is_required = entry['is_required']
            question.choices = entry['choices'] if is_multiple_choice else []
            question.allows_multiple_answers = entry['allows_multiple_answers'] if is_multiple_choice else False
            question.minimum_selections = entry['minimum_selections'] if question.allows_multiple_answers else None
            question.maximum_selections = entry['maximum_selections'] if question.allows_multiple_answers else None
            question.order = order
            question.save()

        for question_id, question in questions_by_id.items():
            if question_id not in kept_question_ids and not question.is_archived:
                question.retire()

    def duplicate(self, owner, title):
        duplicated_form = Form.objects.create(
            owner=owner,
            title=title[:Form._meta.get_field('title').max_length],
            description=self.description,
            status=self.status,
        )
        Question.objects.bulk_create([
            Question(
                form=duplicated_form,
                label=question.label,
                description=question.description,
                answer_type=question.answer_type,
                is_required=question.is_required,
                choices=list(question.choices),
                allows_multiple_answers=question.allows_multiple_answers,
                minimum_selections=question.minimum_selections,
                maximum_selections=question.maximum_selections,
                order=order,
            )
            for order, question in enumerate(self.get_active_questions(), start=1)
        ])
        return duplicated_form

    def record_response(self, response_form, user, context=(), context_key=''):
        response = self.responses.create(
            user=user,
            context=build_response_context(context),
            context_key=context_key,
        )
        Answer.objects.bulk_create([
            Answer(response=response, **answer_fields)
            for answer_fields in response_form.get_answer_fields()
        ])
        return response


def build_response_context(context):
    return [{'label': label, 'value': value} for label, value in context]


class Question(models.Model):
    class AnswerType(models.TextChoices):
        TEXT = 'text', _('Text')
        NUMBER = 'number', _('Number')
        DECK_LINK = 'deck_link', _('Deck link')
        MULTIPLE_CHOICE = 'multiple_choice', _('Multiple choice')
        CHECKBOX = 'checkbox', _('Checkbox')

    form = models.ForeignKey(
        Form, on_delete=models.CASCADE, related_name='questions')
    label = models.CharField(max_length=QUESTION_LABEL_MAX_LENGTH)
    description = models.TextField(default='', blank=True)
    answer_type = models.CharField(
        max_length=20, choices=AnswerType.choices, default=AnswerType.TEXT)
    is_required = models.BooleanField(default=False)
    choices = models.JSONField(default=list, blank=True)
    allows_multiple_answers = models.BooleanField(default=False)
    minimum_selections = models.PositiveSmallIntegerField(null=True, blank=True)
    maximum_selections = models.PositiveSmallIntegerField(null=True, blank=True)
    order = models.PositiveIntegerField(default=1)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.label

    def get_field_name(self):
        return f'question_{self.id}'

    def archive(self):
        self.is_archived = True
        self.save(update_fields=['is_archived'])

    def retire(self):
        if self.answers.exists():
            self.archive()
        else:
            self.delete()

    def get_answer_fields(self, cleaned_value):
        if self.answer_type == self.AnswerType.CHECKBOX:
            return {'value': 'Yes' if cleaned_value else 'No'}
        if cleaned_value in (None, '', []):
            return None
        if self.allows_multiple_answers:
            return {'value': ANSWER_SELECTION_SEPARATOR.join(cleaned_value)}
        if self.answer_type == self.AnswerType.NUMBER:
            return {'value': format_decimal_answer(cleaned_value)}
        if self.answer_type == self.AnswerType.DECK_LINK:
            return {'value': cleaned_value['url'], 'deck_id': cleaned_value['deck_id']}
        return {'value': cleaned_value}

    def to_builder_entry(self):
        return {
            'id': self.id,
            'label': self.label,
            'description': self.description,
            'answer_type': self.answer_type,
            'is_required': self.is_required,
            'choices': list(self.choices),
            'allows_multiple_answers': self.allows_multiple_answers,
            'minimum_selections': self.minimum_selections,
            'maximum_selections': self.maximum_selections,
        }


def describe_selection_limits(minimum_selections, maximum_selections):
    if minimum_selections and minimum_selections == maximum_selections:
        return f'Choose exactly {pluralize_options(minimum_selections)}.'
    if minimum_selections and maximum_selections:
        return f'Choose between {minimum_selections} and {maximum_selections} options.'
    if minimum_selections:
        return f'Choose at least {pluralize_options(minimum_selections)}.'
    if maximum_selections:
        return f'Choose at most {pluralize_options(maximum_selections)}.'
    return ''


def pluralize_options(option_count):
    return f'{option_count} option' if option_count == 1 else f'{option_count} options'


def format_decimal_answer(value):
    normalized_value = Decimal(value).normalize()
    return format(normalized_value, 'f')


class Response(models.Model):
    form = models.ForeignKey(
        Form, on_delete=models.CASCADE, related_name='responses')
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ghostform_responses')
    submitted_on = models.DateTimeField(auto_now_add=True)
    context_key = models.CharField(
        max_length=100, default='', blank=True, db_index=True)
    context = models.JSONField(default=list, blank=True)
    is_context_removed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-submitted_on', '-id']

    def __str__(self):
        return f'{self.form.title} - {self.submitted_on:%Y-%m-%d %H:%M}'


class Answer(models.Model):
    response = models.ForeignKey(
        Response, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(
        Question, on_delete=models.RESTRICT, related_name='answers')
    value = models.TextField(default='', blank=True)
    deck_id = models.UUIDField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['response', 'question'], name='ghostform_unique_answer_per_question'),
        ]

    def __str__(self):
        return f'{self.question.label}: {self.value}'
