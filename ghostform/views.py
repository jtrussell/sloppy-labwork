import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from decks.models import House, Set
from .exports import write_responses_csv
from .forms import FormDetailsForm, QuestionsPayloadForm
from .hooks import get_response_form
from .models import Form, Question, MAXIMUM_QUESTIONS_PER_FORM
from .picker import search_pickable_forms


FORMS_PER_PAGE = 20


def get_editable_form_or_403(user, form_code):
    ghostform = get_object_or_404(Form, code=form_code)
    if not ghostform.can_edit(user):
        raise PermissionDenied
    return ghostform


def get_viewable_form_or_403(user, form_code):
    ghostform = get_object_or_404(Form, code=form_code)
    if not ghostform.can_view_responses(user):
        raise PermissionDenied
    return ghostform


@login_required
def form_list(request):
    owned_forms = Form.objects.filter(owner=request.user).annotate(
        response_count=Count('responses', distinct=True),
        latest_response_on=Max('responses__submitted_on'),
        question_count=Count(
            'questions', filter=Q(questions__is_archived=False), distinct=True),
    ).order_by('-updated_on', '-id')
    forms_page = Paginator(owned_forms, FORMS_PER_PAGE).get_page(
        request.GET.get('page', 1))
    return render(request, 'ghostform/list.html', {'forms_page': forms_page})


@login_required
def form_create(request):
    return render_form_builder(request, None)


@login_required
def form_edit(request, form_code):
    ghostform = get_editable_form_or_403(request.user, form_code)
    return render_form_builder(request, ghostform)


def get_submitted_question_entries(post_data, fallback_entries):
    try:
        submitted_entries = json.loads(post_data.get('questions_payload', ''))
    except (TypeError, ValueError):
        return fallback_entries
    if not isinstance(submitted_entries, list):
        return fallback_entries
    return [entry for entry in submitted_entries if isinstance(entry, dict)]


def get_builder_choice_presets():
    return {
        'houses': list(House.objects.order_by('name').values_list('name', flat=True)),
        'sets': list(Set.objects.filter(is_tournament_legal=True).order_by('id').values_list('name', flat=True)),
    }


def render_form_builder(request, ghostform):
    stored_question_entries = [
        question.to_builder_entry() for question in ghostform.get_active_questions()
    ] if ghostform else []

    if request.method == 'POST':
        details_form = FormDetailsForm(request.POST, instance=ghostform)
        questions_form = QuestionsPayloadForm(request.POST)
        if details_form.is_valid() and questions_form.is_valid():
            with transaction.atomic():
                saved_form = details_form.save(commit=False)
                if not saved_form.owner_id:
                    saved_form.owner = request.user
                saved_form.save()
                saved_form.sync_questions(
                    questions_form.cleaned_data['questions_payload'])
            messages.success(
                request, f'Form "{saved_form.title}" saved.')
            return redirect('ghostform:ghostform-detail', form_code=saved_form.code)
        question_entries = get_submitted_question_entries(
            request.POST, stored_question_entries)
    else:
        details_form = FormDetailsForm(instance=ghostform)
        questions_form = QuestionsPayloadForm()
        question_entries = stored_question_entries

    return render(request, 'ghostform/builder.html', {
        'ghostform': ghostform,
        'details_form': details_form,
        'questions_form': questions_form,
        'builder_config': {
            'questions': question_entries,
            'answer_types': [
                {'value': value, 'label': label}
                for value, label in Question.AnswerType.choices
            ],
            'choice_presets': get_builder_choice_presets(),
            'maximum_questions': MAXIMUM_QUESTIONS_PER_FORM,
        },
    })


@login_required
def form_detail(request, form_code):
    ghostform = get_viewable_form_or_403(request.user, form_code)
    response_stats = ghostform.responses.aggregate(
        response_count=Count('id'), latest_response_on=Max('submitted_on'))
    return render(request, 'ghostform/detail.html', {
        'ghostform': ghostform,
        'questions': ghostform.get_active_questions(),
        'can_edit': ghostform.can_edit(request.user),
        **response_stats,
    })


@login_required
@require_POST
def form_update_status(request, form_code):
    ghostform = get_editable_form_or_403(request.user, form_code)
    requested_status = request.POST.get('status')

    if requested_status not in Form.Status.values:
        messages.error(request, 'Unknown form status.')
    elif requested_status == Form.Status.PUBLISHED and not ghostform.get_active_questions().exists():
        messages.error(request, 'Add at least one question before publishing.')
    else:
        ghostform.status = requested_status
        ghostform.save(update_fields=['status', 'updated_on'])
        messages.success(
            request, f'Form is now {ghostform.get_status_display().lower()}.')

    return redirect('ghostform:ghostform-detail', form_code=ghostform.code)


@login_required
def form_responses_csv(request, form_code):
    ghostform = get_viewable_form_or_403(request.user, form_code)
    filename = slugify(ghostform.title) or ghostform.code
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}-responses.csv"'},
    )
    write_responses_csv(ghostform, response)
    return response


@login_required
def form_picker_results(request):
    query = request.GET.get('q', '').strip()
    return render(request, 'ghostform/partials/form-picker-results.html', {
        'results': search_pickable_forms(request.user, query),
        'query': query,
    })


@login_required
def form_picker_preview(request, form_code):
    ghostform = get_viewable_form_or_403(request.user, form_code)
    return render(request, 'ghostform/partials/form-picker-preview.html', {
        'ghostform': ghostform,
        'questions': ghostform.get_active_questions(),
    })


@login_required
def form_fill(request, form_code):
    ghostform = get_object_or_404(Form, code=form_code)
    is_preview = ghostform.status == Form.Status.DRAFT
    if is_preview and not ghostform.can_edit(request.user):
        raise Http404

    if request.method == 'POST' and ghostform.is_accepting_responses():
        response_form = get_response_form(ghostform, request.POST)
        if response_form.is_valid():
            ghostform.record_response(response_form, request.user)
            return redirect('ghostform:ghostform-fill-thanks', form_code=ghostform.code)
    elif request.method == 'POST':
        messages.error(request, 'This form is not accepting responses.')
        return redirect('ghostform:ghostform-fill', form_code=ghostform.code)
    else:
        response_form = get_response_form(ghostform)

    return render(request, 'ghostform/fill.html', {
        'ghostform': ghostform,
        'response_form': response_form,
        'is_preview': is_preview,
        'can_edit': ghostform.can_edit(request.user),
    })


@login_required
def form_fill_thanks(request, form_code):
    ghostform = get_object_or_404(
        Form, code=form_code, status__in=[Form.Status.PUBLISHED, Form.Status.CLOSED])
    return render(request, 'ghostform/fill-thanks.html', {'ghostform': ghostform})
