import re
from dataclasses import dataclass
from pathlib import Path

from django import forms
from django.contrib.auth.decorators import user_passes_test
from django.contrib.staticfiles import finders
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render

from .models import PmcProfile

TOKENS_STYLESHEET = 'pmc/css/system/tokens.css'
COMMENT = re.compile(r'/\*.*?\*/', re.S)
DECLARATION = re.compile(r'(--[a-z0-9-]+)\s*:\s*([^;]+);')
RULE = re.compile(r'^([^{}\n][^{}]*?)\s*\{([^{}]*)\}', re.M)
THEME_SELECTOR = re.compile(r'\[data-theme="(\d+)"\]')
DEFAULT_THEME = str(PmcProfile.ThemeOptions.KEYCHAIN_DARK.value)

SECTIONS = (
    ('foundations', 'Foundations'),
    ('components', 'Components'),
    ('forms', 'Forms'),
    ('data', 'Tables and lists'),
    ('staff', 'Staff'),
    ('feedback', 'Feedback and dialogs'),
    ('patterns', 'Page patterns'),
)
SECTION_TITLES = dict(SECTIONS)
NAV_ICON_NAMES = (
    'keychain', 'home', 'calendar', 'users', 'flag', 'leaderboard', 'results', 'award', 'news', 'more',
)
UTILITY_ICON_NAMES = (
    'close', 'chevron-left', 'chevron-right', 'check', 'lock', 'pin', 'plus', 'edit', 'trash', 'qr', 'external',
    'shield', 'drag', 'map', 'target', 'shield-check', 'stairs', 'flame',
)


@dataclass(frozen=True)
class Token:
    name: str
    value: str

    @property
    def group_key(self):
        return self.name[2:].split('-')[0]


def read_tokens_stylesheet():
    path = finders.find(TOKENS_STYLESHEET)
    if path is None:
        raise ImproperlyConfigured(f'{TOKENS_STYLESHEET} was not found by the staticfiles finders')
    return Path(path).read_text(encoding='utf-8')


def _rules(css):
    for selector, body in RULE.findall(COMMENT.sub('', css)):
        yield [part.strip() for part in selector.split(',')], body


def _declarations(body):
    return [Token(name, ' '.join(value.split())) for name, value in DECLARATION.findall(body)]


def static_tokens(css=None):
    css = css if css is not None else read_tokens_stylesheet()
    return [token for selectors, body in _rules(css) if selectors == [':root'] for token in _declarations(body)]


def theme_tokens(css=None):
    css = css if css is not None else read_tokens_stylesheet()
    themes = {}
    for selectors, body in _rules(css):
        theme_numbers = [match.group(1) for part in selectors if (match := THEME_SELECTOR.fullmatch(part))]
        if len(theme_numbers) == 1:
            themes[theme_numbers[0]] = _declarations(body)
    return themes


def tokens_by_group(tokens):
    grouped = {}
    for token in tokens:
        grouped.setdefault(token.group_key, []).append(token)
    return grouped


class GalleryDemoForm(forms.Form):
    event_name = forms.CharField(label='Event name', help_text='Shown on the event page and in results.')
    event_format = forms.ChoiceField(
        label='Format', choices=[('archon', 'Archon'), ('sealed', 'Sealed'), ('alliance', 'Alliance')])
    start_date = forms.DateField(label='Start date', widget=forms.DateInput(attrs={'type': 'date'}))
    player_cap = forms.IntegerField(label='Player cap', required=False, min_value=2)
    description = forms.CharField(label='Description', required=False, widget=forms.Textarea(attrs={'rows': 3}))
    results_file = forms.FileField(label='Results file', required=False)
    is_casual = forms.BooleanField(label='Casual event', required=False, help_text='Casual events award no RP.')
    visibility = forms.ChoiceField(
        label='Visibility', widget=forms.RadioSelect, choices=[('members', 'Members only'), ('public', 'Public')])
    tags = forms.MultipleChoiceField(
        label='Tags', required=False, widget=forms.CheckboxSelectMultiple,
        choices=[('store', 'Store championship'), ('league', 'League night'), ('online', 'Online')])


def invalid_gallery_demo_form():
    form = GalleryDemoForm(
        prefix='invalid',
        data={'invalid-event_name': '', 'invalid-event_format': 'archon', 'invalid-start_date': 'soon'})
    form.is_valid()
    form.add_error(None, 'This event overlaps another event in the playgroup.')
    return form


def _themeable_token_rows(css):
    tokens_by_theme = theme_tokens(css)
    theme_numbers = [str(value) for value, _ in PmcProfile.ThemeOptions.choices]
    values_by_theme = {
        theme_number: {token.name: token.value for token in tokens_by_theme.get(theme_number, [])}
        for theme_number in theme_numbers
    }
    return [
        {
            'token': token,
            'values': [(theme_number, values_by_theme[theme_number].get(token.name)) for theme_number in theme_numbers],
        }
        for token in tokens_by_theme.get(DEFAULT_THEME, [])
    ]


def _gallery_context(section_slug=None):
    css = read_tokens_stylesheet()
    return {
        'sections': SECTIONS,
        'current_section': section_slug,
        'section_title': SECTION_TITLES.get(section_slug),
        'themes': PmcProfile.ThemeOptions.choices,
        'static_tokens_by_group': tokens_by_group(static_tokens(css)),
        'themeable_token_rows': _themeable_token_rows(css),
        'nav_icon_names': NAV_ICON_NAMES,
        'utility_icon_names': UTILITY_ICON_NAMES,
        'demo_form': GalleryDemoForm(),
        'invalid_demo_form': invalid_gallery_demo_form(),
        'demo_page': Paginator(range(95), 10).page(3),
    }


def _is_django_staff_or_refused(user):
    if user.is_authenticated and not user.is_staff:
        raise PermissionDenied
    return user.is_authenticated


django_staff_required = user_passes_test(_is_django_staff_or_refused)


@django_staff_required
def index(request):
    return render(request, 'pmc/ds-index.html', _gallery_context())


@django_staff_required
def section(request, section_slug):
    if section_slug not in SECTION_TITLES:
        raise Http404
    return render(request, f'pmc/ds-{section_slug}.html', _gallery_context(section_slug))
