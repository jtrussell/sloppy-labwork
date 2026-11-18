import re
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.template import Context, Template, TemplateSyntaxError
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .design_system import SECTION_TITLES, invalid_gallery_demo_form, static_tokens, theme_tokens
from .models import PmcProfile

SIMPLE_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
DEFAULT_THEME = str(PmcProfile.ThemeOptions.KEYCHAIN_DARK.value)


class ThemeTokenTests(SimpleTestCase):
    def test_every_profile_theme_has_a_token_block(self):
        defined_themes = set(theme_tokens())
        for value, label in PmcProfile.ThemeOptions.choices:
            self.assertIn(str(value), defined_themes, f'{label} has no [data-theme="{value}"] block')

    def test_every_theme_defines_the_same_themeable_tokens(self):
        themes = theme_tokens()
        default_names = {token.name for token in themes[DEFAULT_THEME]}
        for theme, tokens in themes.items():
            self.assertEqual({token.name for token in tokens}, default_names, f'theme {theme} token set differs')

    def test_themeable_tokens_are_not_redefined_as_static_tokens(self):
        themeable_names = {token.name for token in theme_tokens()[DEFAULT_THEME]}
        static_names = {token.name for token in static_tokens()}
        self.assertFalse(themeable_names & static_names)


class StylesheetConventionTests(SimpleTestCase):
    TOKEN_BASED_STYLESHEETS = ('*.css', 'system/*.css')
    TOKENS_STYLESHEET_NAME = 'tokens.css'
    COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)
    DECLARATION_VALUE = re.compile(r'[\w-]+\s*:\s*([^;{}]+)[;}]')
    RAW_COLOR = re.compile(r'#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(')

    def token_based_stylesheets(self):
        stylesheet_directory = Path(settings.BASE_DIR) / 'static' / 'pmc' / 'css'
        for pattern in self.TOKEN_BASED_STYLESHEETS:
            for path in sorted(stylesheet_directory.glob(pattern)):
                if path.name != self.TOKENS_STYLESHEET_NAME:
                    yield path

    def test_stylesheets_are_found(self):
        names = {path.name for path in self.token_based_stylesheets()}
        self.assertIn('components.css', names)
        self.assertNotIn(self.TOKENS_STYLESHEET_NAME, names)

    def test_colors_come_from_tokens(self):
        for path in self.token_based_stylesheets():
            css = self.COMMENT.sub('', path.read_text(encoding='utf-8'))
            raw_colors = [value.strip() for value in self.DECLARATION_VALUE.findall(css)
                          if self.RAW_COLOR.search(value)]
            self.assertEqual(raw_colors, [], f'{path.name} uses raw colors instead of tokens')


@override_settings(STORAGES=SIMPLE_STORAGES)
class GalleryAccessTests(TestCase):
    def test_anonymous_visitors_are_sent_to_log_in(self):
        response = self.client.get(reverse('pmc-design-system'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(settings.LOGIN_URL, response['Location'])

    def test_players_are_refused(self):
        self.client.force_login(User.objects.create_user('player', password='password'))
        response = self.client.get(reverse('pmc-design-system'))
        self.assertEqual(response.status_code, 403)

    def test_django_staff_can_view_every_section(self):
        self.client.force_login(User.objects.create_user('staff', password='password', is_staff=True))
        self.assertEqual(self.client.get(reverse('pmc-design-system')).status_code, 200)
        for section_slug in SECTION_TITLES:
            response = self.client.get(reverse('pmc-design-system-section', args=[section_slug]))
            self.assertEqual(response.status_code, 200, section_slug)

    def test_unknown_section_is_not_found(self):
        self.client.force_login(User.objects.create_user('staff', password='password', is_staff=True))
        response = self.client.get(reverse('pmc-design-system-section', args=['nope']))
        self.assertEqual(response.status_code, 404)


class GalleryExampleTagTests(SimpleTestCase):
    def test_unknown_flag_is_a_syntax_error(self):
        with self.assertRaises(TemplateSyntaxError):
            Template('{% load pmc_extras %}{% kc_example nomarkup %}x{% end_kc_example %}')

    def test_example_renders_preview_and_escaped_markup(self):
        rendered = Template(
            '{% load pmc_extras %}{% kc_example %}<b>{{ label }}</b>{% end_kc_example %}'
        ).render(Context({'label': 'Bold'}))
        self.assertIn('<b>Bold</b>', rendered)
        self.assertIn('&lt;b&gt;Bold&lt;/b&gt;', rendered)


class FormFieldsIncludeTests(SimpleTestCase):
    def test_hidden_field_errors_are_shown_with_form_errors(self):
        class FormWithHiddenField(forms.Form):
            token = forms.CharField(widget=forms.HiddenInput)

        form = FormWithHiddenField(data={})
        form.is_valid()
        rendered = render_to_string('pmc/_form-fields.html', {'form': form})
        self.assertIn('(Hidden field token) This field is required.', rendered)

    def test_field_errors_are_described_by_their_input(self):
        form = invalid_gallery_demo_form()
        rendered = render_to_string('pmc/_field.html', {'field': form['event_name']})
        self.assertIn(f'id="{form["event_name"].auto_id}_error"', rendered)
        self.assertIn(f'{form["event_name"].auto_id}_error', form['event_name'].aria_describedby)

    def test_help_text_is_escaped(self):
        class FormWithUserHelpText(forms.Form):
            answer = forms.CharField(help_text='<img src=x onerror=alert(1)>')

        rendered = render_to_string('pmc/_field.html', {'field': FormWithUserHelpText()['answer']})
        self.assertNotIn('<img src=x', rendered)
        self.assertIn('&lt;img src=x', rendered)


class MessagesIncludeTests(SimpleTestCase):
    def test_only_warnings_and_errors_wait_to_be_dismissed(self):
        rendered_by_level = {
            level: render_to_string('pmc/_message.html', {'level': level, 'text': 'Saved.'})
            for level in ['success', 'info', 'warning', 'error']
        }
        persistent_levels = [
            level for level, rendered in rendered_by_level.items() if 'data-message-persistent' in rendered
        ]
        self.assertEqual(persistent_levels, ['warning', 'error'])

    def test_message_text_is_escaped(self):
        rendered = render_to_string('pmc/_message.html', {'level': 'error', 'text': '<img src=x>'})
        self.assertNotIn('<img src=x', rendered)
        self.assertIn('&lt;img src=x', rendered)


class NavigationIncludeTests(SimpleTestCase):
    def nav_links(self, count):
        return [{'name': f'Link {number}', 'url': f'/link-{number}/', 'icon': 'home'} for number in range(1, count + 1)]

    def test_five_links_all_fit_on_the_tab_bar(self):
        rendered = render_to_string('pmc/_nav.html', {'nav_links': self.nav_links(5)})
        self.assertNotIn('primary-nav__entry--overflow', rendered)
        self.assertNotIn('primary-nav__more', rendered)

    def test_sixth_link_moves_behind_more_in_the_order_given(self):
        rendered = render_to_string('pmc/_nav.html', {'nav_links': self.nav_links(6)})
        self.assertEqual(rendered.count('primary-nav__entry--overflow'), 2)
        sheet = rendered.split('primary-nav__sheet"')[1]
        self.assertNotIn('Link 4', sheet)
        self.assertLess(sheet.index('Link 5'), sheet.index('Link 6'))
