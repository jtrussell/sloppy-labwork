from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from django_htmx.http import reswap, retarget

from common.auth import teammate_required
from user_profile.models import UserProfile

from .forms import ComponentDemoForm, DialogDemoForm, invalid_component_demo_form
from .tokens import (
    derived_tokens, medium_breakpoint_tokens, read_tokens_stylesheet, root_tokens, theme_tokens, tokens_by_group
)

SECTION_GROUPS = (
    ('Foundations', (
        ('color', 'Color'),
        ('typography', 'Typography'),
        ('spacing', 'Spacing'),
        ('shape', 'Shape & elevation'),
    )),
    ('Components', (
        ('buttons', 'Buttons'),
        ('forms', 'Forms'),
        ('feedback', 'Feedback'),
        ('containers', 'Containers'),
        ('navigation', 'Navigation'),
        ('interactive', 'Interactive'),
        ('dialogs', 'Dialogs'),
    )),
    ('Guides', (
        ('theming', 'Theming'),
        ('layout', 'Layout & alignment'),
        ('patterns', 'Page patterns'),
    )),
)

DEMO_STEPS = (
    {'label': 'Pick', 'icon': 'deck', 'is_done': True},
    {'label': 'Ban', 'icon': 'ban', 'is_done': True},
    {'label': 'Game 1', 'icon': 'play', 'is_current': True, 'detail': 'In progress'},
    {'label': 'Game 2', 'icon': 'play'},
    {'label': 'Swap', 'icon': 'swap', 'is_blocked': True},
)


def _forms_context():
    return {'demo_form': ComponentDemoForm(), 'invalid_demo_form': invalid_component_demo_form()}


def _navigation_context():
    return {'demo_page': Paginator(range(95), 10).page(3), 'demo_steps': DEMO_STEPS}


SECTION_CONTEXT_BUILDERS = {
    'forms': _forms_context,
    'navigation': _navigation_context,
    'patterns': _navigation_context,
}

SECTION_TITLES = {slug: title for _, sections in SECTION_GROUPS for slug, title in sections}


def _themeable_token_rows(css):
    tokens_by_theme = theme_tokens(css)
    theme_numbers = [str(value) for value, _ in UserProfile.ThemeOptions.choices]
    values_by_theme = {
        theme_number: {token.name: token.value for token in tokens_by_theme.get(theme_number, [])}
        for theme_number in theme_numbers
    }
    return [
        {
            'token': token,
            'values': [(theme_number, values_by_theme[theme_number].get(token.name)) for theme_number in theme_numbers],
        }
        for token in tokens_by_theme.get('0', [])
    ]


def _gallery_context(section_slug=None):
    css = read_tokens_stylesheet()
    tokens = root_tokens(css)
    derived = derived_tokens(css)
    return {
        'section_groups': SECTION_GROUPS,
        'current_section': section_slug,
        'section_title': SECTION_TITLES.get(section_slug),
        'themes': UserProfile.ThemeOptions.choices,
        'tokens_by_group': tokens_by_group(tokens),
        'themeable_token_rows': _themeable_token_rows(css),
        'medium_breakpoint_tokens': medium_breakpoint_tokens(css),
        'derived_tokens': derived,
    }


@teammate_required
def index(request):
    return render(request, 'design_system/index.html', _gallery_context())


@teammate_required
def section(request, section_slug):
    if section_slug not in SECTION_TITLES:
        raise Http404
    context = _gallery_context(section_slug)
    if section_slug in SECTION_CONTEXT_BUILDERS:
        context.update(SECTION_CONTEXT_BUILDERS[section_slug]())
    return render(request, f'design_system/{section_slug}.html', context)


@teammate_required
def dialog_demo(request):
    form = DialogDemoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        return render(request, 'design_system/partials/dialog-demo-result.html', {'deck_name': form.cleaned_data['deck_name']})
    response = render(request, 'design_system/partials/dialog-demo-form.html', {'form': form})
    if request.method == 'POST':
        return reswap(retarget(response, '#dialog'), 'innerHTML')
    return response
