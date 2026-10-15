import csv
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .models import ANSWER_SELECTION_SEPARATOR, CSV_SELECTION_DELIMITER, Question


SPREADSHEET_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def make_spreadsheet_safe(value):
    if not isinstance(value, str) or not value.startswith(SPREADSHEET_FORMULA_PREFIXES):
        return value
    try:
        Decimal(value)
        return value
    except InvalidOperation:
        return "'" + value


def format_export_timestamp(value):
    return timezone.localtime(value).strftime('%Y-%m-%d %H:%M:%S')


def get_context_labels(responses):
    context_labels = []
    for response in responses:
        for item in response.context:
            label = item.get('label')
            if label and label not in context_labels:
                context_labels.append(label)
    return context_labels


def get_question_headers(question):
    label = f'{question.label} (archived)' if question.is_archived else question.label
    if question.answer_type == Question.AnswerType.DECK_LINK:
        return [label, f'{label} (Deck ID)']
    return [label]


def get_question_cells(question, answer):
    value = answer.value if answer else ''
    if question.answer_type == Question.AnswerType.DECK_LINK:
        deck_id = str(answer.deck_id) if answer and answer.deck_id else ''
        return [value, deck_id]
    if question.answer_type == Question.AnswerType.MULTIPLE_CHOICE:
        return [CSV_SELECTION_DELIMITER.join(value.split(ANSWER_SELECTION_SEPARATOR))]
    return [value]


def write_responses_csv(form, output):
    questions = form.get_questions_for_export()
    responses = list(
        form.responses.select_related('user').prefetch_related('answers').order_by('submitted_on', 'id'))
    context_labels = get_context_labels(responses)
    has_linked_responses = any(response.context_key for response in responses)

    header = ['Submitted at', 'User', *context_labels]
    if has_linked_responses:
        header.append('Linked record removed')
    for question in questions:
        header.extend(get_question_headers(question))

    writer = csv.writer(output)
    writer.writerow([make_spreadsheet_safe(cell) for cell in header])

    for response in responses:
        context_values = {item.get('label'): item.get('value') for item in response.context}
        answers_by_question_id = {answer.question_id: answer for answer in response.answers.all()}

        row = [
            format_export_timestamp(response.submitted_on),
            response.user.username if response.user else '',
        ]
        row.extend(context_values.get(label, '') for label in context_labels)
        if has_linked_responses:
            row.append('Yes' if response.is_context_removed else '')
        for question in questions:
            row.extend(get_question_cells(question, answers_by_question_id.get(question.id)))

        writer.writerow([make_spreadsheet_safe('' if cell is None else cell) for cell in row])
