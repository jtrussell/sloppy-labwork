from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django_htmx.http import reswap, retarget

from lineups.models import Lineup, LineupVersion

from . import engine
from .forms import (
    DeckLineupForm, DeckLinksForm, PickForm, PlayResultForm, TemplateDetailsForm,
    apply_builder_action, default_builder_steps, parse_builder_steps,
)
from .models import Session, SessionTemplate
from .session_view import ACTION_ICONS, ActionState, build_session_view, template_rail, template_summary

SESSION_PAGE = 'trade_secrets/session-detail.html'
SOURCE_LINKS = 'links'
SOURCE_LINEUP = 'lineup'


def redirect_to(request, url):
    if request.htmx:
        response = HttpResponse(url)
        response['HX-Redirect'] = url
        return response
    return redirect(url)


def session_url(session):
    return reverse('trade_secrets:session-detail', args=[session.code])


def validation_messages(error):
    return list(error.messages)


def template_card(template):
    return {
        'template': template,
        'rail': template_rail(template.step_specs),
        'summary': template_summary(template.step_specs),
    }


def home(request):
    templates = SessionTemplate.usable_by(request.user).prefetch_related('steps')
    archived_templates = (
        SessionTemplate.objects.filter(owner=request.user, archived_on__isnull=False)
        if request.user.is_authenticated else SessionTemplate.objects.none())
    return render(request, 'trade_secrets/home.html', {
        'system_templates': [template_card(template) for template in templates if template.is_system],
        'own_templates': [template_card(template) for template in templates if not template.is_system],
        'archived_templates': archived_templates,
    })


def step_detail(step):
    if step.is_matchup_ban:
        return 'Each player bans one matchup; banned matchups are not played'
    if step.is_play:
        return f'Played decks eligible again: {engine.PlayedDeckRule(step.played_deck_rule).label}'
    return engine.wave_detail(step)


def builder_rows(steps):
    traces = {trace.order: trace for trace in engine.simulate_template_steps(steps)}
    return [
        {
            'index': step.order,
            'spec': step,
            'label': engine.step_label(steps, step) if not step.is_submit else str(engine.Action.SUBMIT.label),
            'icon': ACTION_ICONS[step.action],
            'trace': traces.get(step.order),
            'is_first': step.order == 0,
            'is_last': step.order == len(steps) - 1,
            'quantity_maximum': (
                engine.MAXIMUM_DECKS_PER_PLAYER if step.is_submit else engine.MAXIMUM_STEP_QUANTITY),
        }
        for step in steps
    ]


@login_required
@require_http_methods(['GET', 'POST'])
def template_create(request):
    if request.method == 'POST':
        builder_action = request.POST.get('builder_action', '')
        is_saving = builder_action == 'save'
        steps = apply_builder_action(parse_builder_steps(request.POST), builder_action)
        details_form = TemplateDetailsForm(request.POST) if is_saving else TemplateDetailsForm(
            initial={'name': request.POST.get('name', ''), 'description': request.POST.get('description', '')})
    else:
        is_saving = False
        steps = default_builder_steps()
        details_form = TemplateDetailsForm()

    errors = engine.validate_template_steps(steps)
    if is_saving and details_form.is_valid() and not errors:
        template = SessionTemplate.create_with_steps(
            request.user,
            details_form.cleaned_data['name'],
            details_form.cleaned_data['description'],
            steps,
        )
        return redirect_to(request, reverse('trade_secrets:template-detail', args=[template.code]))

    step_error_messages = {trace.error for trace in engine.simulate_template_steps(steps) if trace.error}
    context = {
        'details_form': details_form,
        'rows': builder_rows(steps),
        'summary_errors': [error for error in errors if error not in step_error_messages],
        'is_valid': not errors,
        'can_add_step': len(steps) < engine.MAXIMUM_STEPS_PER_TEMPLATE,
        'step_actions': [action for action in engine.Action if action != engine.Action.SUBMIT],
        'played_deck_rules': engine.PlayedDeckRule.choices,
    }
    template_name = 'trade_secrets/template-builder.html'
    if request.htmx:
        template_name += '#builder'
    return render(request, template_name, context)


def get_viewable_template(request, template_code):
    template = get_object_or_404(SessionTemplate, code=template_code)
    if not template.can_view(request.user):
        raise Http404
    return template


def template_detail(request, template_code):
    template = get_object_or_404(SessionTemplate, code=template_code)
    if not template.can_view(request.user):
        if template.is_public and not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        raise Http404
    rail = template_rail(template.step_specs)
    return render(request, 'trade_secrets/template-detail.html', {
        'template': template,
        'rows': [
            {'number': rail_step.number, 'icon': rail_step.icon, 'label': rail_step.label, 'detail': step_detail(step)}
            for rail_step, step in zip(rail, template.step_specs)
        ],
        'can_manage': template.can_manage(request.user),
        'is_shared_with_viewer': not template.is_system and not template.is_owned_by(request.user),
        'share_url': request.build_absolute_uri(reverse('trade_secrets:template-detail', args=[template.code])),
        'can_delete': template.can_delete(request.user),
        'can_start': template.can_start_session(request.user),
        'visibility_choices': SessionTemplate.Visibility.choices,
        'session_count': template.sessions.count(),
    })


@login_required
@require_POST
def template_archive(request, template_code):
    template = get_viewable_template(request, template_code)
    if not template.can_manage(request.user):
        raise PermissionDenied
    if template.is_archived:
        template.unarchive()
        messages.success(request, f'"{template.name}" is back in your templates.')
    else:
        template.archive()
        messages.success(request, f'"{template.name}" is archived.')
    return redirect_to(request, reverse('trade_secrets:template-detail', args=[template.code]))


@login_required
@require_POST
def template_visibility(request, template_code):
    template = get_viewable_template(request, template_code)
    if not template.can_manage(request.user):
        raise PermissionDenied
    try:
        template.set_visibility(request.POST.get('visibility', ''))
    except ValidationError as error:
        messages.error(request, ' '.join(validation_messages(error)))
        return redirect_to(request, reverse('trade_secrets:template-detail', args=[template.code]))
    messages.success(request, f'"{template.name}" is now {template.get_visibility_display().lower()}.')
    return redirect_to(request, reverse('trade_secrets:template-detail', args=[template.code]))


@login_required
@require_POST
def template_delete(request, template_code):
    template = get_viewable_template(request, template_code)
    if not template.can_delete(request.user):
        raise PermissionDenied
    name = template.name
    template.delete()
    messages.success(request, f'"{name}" was deleted.')
    return redirect_to(request, reverse('trade_secrets:home'))


@login_required
@require_POST
def session_create(request):
    template = get_object_or_404(SessionTemplate, code=request.POST.get('template_code', ''))
    if not template.can_start_session(request.user):
        raise PermissionDenied
    session = Session.objects.create(template=template, host=request.user)
    return redirect(session_url(session))


@login_required
@require_GET
def lineup_versions(request):
    lineup = Lineup.objects.filter(owner=request.user, pk=parse_integer(request.GET.get('lineup'))).first()
    return render(request, 'trade_secrets/partials/version-select.html', {
        'versions': versions_with_deck_counts(lineup),
        'required_count': parse_integer(request.GET.get('count')),
    })


@login_required
@require_GET
def lineup_preview(request):
    version = LineupVersion.objects.filter(
        lineup__owner=request.user, pk=parse_integer(request.GET.get('version'))).first()
    version_decks = (
        version.version_decks.select_related('deck__set', 'deck__house_1', 'deck__house_2', 'deck__house_3')
        if version else [])
    return render(request, 'trade_secrets/partials/lineup-preview.html', {
        'cards': [
            {'deck': version_deck.deck, 'status': engine.DeckStatus.AVAILABLE}
            for version_deck in version_decks
        ],
    })


def parse_integer(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def versions_with_deck_counts(lineup):
    if lineup is None:
        return []
    return list(lineup.versions.annotate(deck_count=Count('version_decks')).order_by('-sort_order'))


def own_lineups(user):
    return list(Lineup.objects.filter(owner=user).order_by('name'))


def session_context(request, session, **extra):
    view = build_session_view(session, request.user, request)
    context = {'view': view, 'session': session}
    if view.action_state == ActionState.SUBMIT_DECKS or view.action_state == ActionState.SUBMIT_DECKS_LOCKED:
        required_count = session.template.deck_count
        lineups = own_lineups(request.user)
        context.update({
            'links_form': DeckLinksForm(required_count=required_count),
            'lineups': lineups,
            'versions': versions_with_deck_counts(lineups[0]) if lineups else [],
            'required_count': required_count,
            'deck_source': SOURCE_LINKS,
        })
    context.update(extra)
    return context


def render_session(request, session, partial=None, status=200, **extra):
    template_name = SESSION_PAGE if partial is None else f'{SESSION_PAGE}#{partial}'
    return render(request, template_name, session_context(request, session, **extra), status=status)


def respond_after_session_action(request, session, action_errors=None, **extra):
    if request.htmx:
        return render_session(request, session, partial='board', action_errors=action_errors or [], **extra)
    if action_errors:
        return render_session(request, session, action_errors=action_errors, **extra)
    return redirect(session_url(session))


def get_session(session_code):
    return get_object_or_404(Session.objects.select_related('template', 'host', 'guest'), code=session_code)


def require_seat(session, user):
    seat = session.seat_for(user)
    if seat is None:
        raise PermissionDenied
    return seat


@never_cache
@require_GET
def session_detail(request, session_code):
    return render_session(request, get_session(session_code))


@never_cache
@require_GET
def session_poll(request, session_code):
    current_version = Session.objects.filter(code=session_code).values_list('version', flat=True).first()
    if current_version is None:
        raise Http404
    if str(current_version) == request.GET.get('v'):
        return HttpResponse(status=204)
    session = get_session(session_code)
    context = session_context(request, session)
    if context['view'].stage_key != request.GET.get('stage'):
        response = render(request, f'{SESSION_PAGE}#board', context)
        return reswap(retarget(response, '#ts-board'), 'outerHTML')
    return render(request, f'{SESSION_PAGE}#overview', context)


@login_required
@require_POST
def session_join(request, session_code):
    session = get_session(session_code)
    try:
        session.join(request.user)
    except ValidationError as error:
        return respond_after_session_action(request, session, validation_messages(error))
    return redirect_to(request, session_url(session))


@login_required
@require_POST
def session_decks(request, session_code):
    session = get_session(session_code)
    seat = require_seat(session, request.user)
    required_count = session.template.deck_count
    source = request.POST.get('source', SOURCE_LINKS)
    if source == SOURCE_LINEUP:
        form = DeckLineupForm(request.POST, user=request.user, required_count=required_count)
    else:
        form = DeckLinksForm(request.POST, required_count=required_count)

    if not form.is_valid():
        form_errors = [error for errors in form.errors.values() for error in errors]
        extra = {'deck_source': source}
        if source == SOURCE_LINKS:
            extra['links_form'] = form
        return respond_after_session_action(request, session, form_errors, **extra)

    try:
        session.submit_decks(
            seat, request.user, form.deck_ids, getattr(form, 'source_version', None))
    except ValidationError as error:
        return respond_after_session_action(request, session, validation_messages(error))
    return respond_after_session_action(request, session)


@login_required
@require_POST
def session_pick(request, session_code):
    session = get_session(session_code)
    seat = require_seat(session, request.user)
    form = PickForm(
        request.POST,
        choice_ids=set(session.decks.values_list('id', flat=True))
        | set(session.template.steps.values_list('order', flat=True)))
    if not form.is_valid():
        return respond_after_session_action(
            request, session, ['That choice cannot be picked for this step.'])
    try:
        session.submit_picks(seat, request.user, form.cleaned_data['step_order'], form.cleaned_data['deck'])
    except ValidationError as error:
        return respond_after_session_action(request, session, validation_messages(error))
    return respond_after_session_action(request, session)


def result_form_context(session, step_order, form):
    step = get_object_or_404(session.template.steps, order=step_order, action=engine.Action.PLAY)
    result = session.results.filter(step=step).first()
    step_specs = session.template.step_specs
    return {
        'session': session,
        'form': form,
        'step_order': step_order,
        'game_label': engine.game_label(step_specs, step_specs[step_order]),
        'has_result': result is not None,
        'warns_about_eligibility': step.played_deck_rule == engine.PlayedDeckRule.LOSING_ONLY,
    }


@login_required
@require_http_methods(['GET', 'POST'])
def session_result(request, session_code, step_order):
    session = get_session(session_code)
    require_seat(session, request.user)
    if not session.is_revealed_game(step_order):
        raise Http404
    seat_names = session.seat_names()

    if request.method == 'GET':
        result = session.results.filter(step__order=step_order).first()
        initial = {
            'winner_seat': result.winner_seat,
            'host_score': result.host_score,
            'guest_score': result.guest_score,
        } if result else {}
        form = PlayResultForm(initial=initial, seat_names=seat_names)
        return render_result_form(request, session, step_order, form)

    form = PlayResultForm(request.POST, seat_names=seat_names)
    if form.is_valid():
        try:
            session.record_result(
                request.user, step_order, form.cleaned_data['winner_seat'],
                form.cleaned_data['host_score'], form.cleaned_data['guest_score'])
            return respond_after_session_action(request, session)
        except ValidationError as error:
            form.add_error(None, error)
    response = render_result_form(request, session, step_order, form)
    if request.htmx:
        response = reswap(retarget(response, '#ts-dialog'), 'innerHTML')
    return response


def render_result_form(request, session, step_order, form):
    template_name = 'trade_secrets/result-form.html'
    if request.htmx:
        template_name += '#form'
    return render(request, template_name, result_form_context(session, step_order, form))


@login_required
@require_POST
def session_result_reset(request, session_code, step_order):
    session = get_session(session_code)
    require_seat(session, request.user)
    try:
        session.reset_result(step_order)
    except ValidationError as error:
        return respond_after_session_action(request, session, validation_messages(error))
    return respond_after_session_action(request, session)
