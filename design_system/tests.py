import re
from pathlib import Path
from unittest.mock import patch

from django.conf import settings

from django import forms
from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.template import Context, Template, TemplateSyntaxError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from user_profile.models import UserProfile

from .forms import invalid_component_demo_form
from .tokens import derived_tokens, root_tokens, theme_tokens
from .views import SECTION_TITLES

SIMPLE_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


class ThemeTokenTests(TestCase):
    def test_every_profile_theme_has_a_token_block(self):
        defined_themes = set(theme_tokens())
        for value, label in UserProfile.ThemeOptions.choices:
            self.assertIn(str(value), defined_themes, f'{label} has no [data-theme="{value}"] block')

    def test_every_theme_defines_the_same_themeable_tokens(self):
        themes = theme_tokens()
        default_names = {token.name for token in themes['0']}
        for theme, tokens in themes.items():
            self.assertEqual({token.name for token in tokens}, default_names, f'theme {theme} token set differs')

    def test_themeable_tokens_are_not_redefined_elsewhere(self):
        themeable_names = {token.name for token in theme_tokens()['0']}
        root_names = [token.name for token in root_tokens()]
        duplicated = {name for name in root_names if root_names.count(name) > 1}
        derived_names = {token.name for token in derived_tokens()}
        self.assertFalse(duplicated & themeable_names)
        self.assertFalse(derived_names & themeable_names)


@override_settings(STORAGES=SIMPLE_STORAGES)
class GalleryAccessTests(TestCase):
    def test_anonymous_visitors_are_refused(self):
        response = self.client.get(reverse('design_system:index'))
        self.assertEqual(response.status_code, 403)

    def test_teammate_can_view_the_gallery(self):
        user = User.objects.create_user('teammate', password='password')
        self.client.force_login(user)
        with patch('common.auth.is_teammate', return_value=True):
            response = self.client.get(reverse('design_system:index'))
        self.assertEqual(response.status_code, 200)

    def test_gallery_requires_a_teammate(self):
        user = User.objects.create_user('player', password='password')
        self.client.force_login(user)
        response = self.client.get(reverse('design_system:index'))
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_view_every_section(self):
        user = User.objects.create_superuser('admin', password='password')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('design_system:index')).status_code, 200)
        for section_slug in SECTION_TITLES:
            response = self.client.get(reverse('design_system:section', args=[section_slug]))
            self.assertEqual(response.status_code, 200, section_slug)

    def test_dialog_demo_rerenders_errors_inside_the_dialog(self):
        user = User.objects.create_superuser('admin', password='password')
        self.client.force_login(user)
        response = self.client.post(reverse('design_system:dialog-demo'), {'deck_name': ''}, HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Retarget'], '#dialog')
        self.assertContains(response, 'field__errors')

    def test_dialog_demo_success_swaps_outside_the_dialog(self):
        user = User.objects.create_superuser('admin', password='password')
        self.client.force_login(user)
        response = self.client.post(reverse('design_system:dialog-demo'), {'deck_name': 'Ironside'}, HTTP_HX_REQUEST='true')
        self.assertNotIn('HX-Retarget', response)
        self.assertContains(response, 'Ironside')

    def test_unknown_section_is_not_found(self):
        user = User.objects.create_superuser('admin', password='password')
        self.client.force_login(user)
        response = self.client.get(reverse('design_system:section', args=['nope']))
        self.assertEqual(response.status_code, 404)


class ExampleTagTests(SimpleTestCase):
    def test_unknown_flag_is_a_syntax_error(self):
        with self.assertRaises(TemplateSyntaxError):
            Template('{% load design_system_extras %}{% ds_example nomarkup %}x{% end_ds_example %}')

    def test_example_renders_preview_and_escaped_markup(self):
        rendered = Template(
            '{% load design_system_extras %}{% ds_example %}<b>{{ label }}</b>{% end_ds_example %}'
        ).render(Context({'label': 'Bold'}))
        self.assertIn('<b>Bold</b>', rendered)
        self.assertIn('&lt;b&gt;Bold&lt;/b&gt;', rendered)


class FormFieldsIncludeTests(SimpleTestCase):
    def test_hidden_field_errors_are_shown_with_form_errors(self):
        class FormWithHiddenField(forms.Form):
            token = forms.CharField(widget=forms.HiddenInput)

        form = FormWithHiddenField(data={})
        form.is_valid()
        rendered = render_to_string('components/form-fields.html', {'form': form})
        self.assertIn('(Hidden field token) This field is required.', rendered)

    def test_field_errors_are_described_by_their_input(self):
        form = invalid_component_demo_form()
        rendered = render_to_string('components/field.html', {'field': form['deck_name']})
        self.assertIn(f'id="{form["deck_name"].auto_id}_error"', rendered)
        self.assertIn(f'{form["deck_name"].auto_id}_error', form['deck_name'].aria_describedby)


class FieldIncludeEscapingTests(SimpleTestCase):
    def test_help_text_is_escaped(self):
        class FormWithUserHelpText(forms.Form):
            answer = forms.CharField(help_text='<img src=x onerror=alert(1)>')

        rendered = render_to_string('components/field.html', {'field': FormWithUserHelpText()['answer']})
        self.assertNotIn('<img src=x', rendered)
        self.assertIn('&lt;img src=x', rendered)


class StylesheetConventionTests(SimpleTestCase):
    EXCLUDED_PARTS = {'.venv', 'staticfiles', 'node_modules', '.local', '.claude', 'vendor', 'pmc'}
    EXCLUDED_NAMES = {'tokens.css', 'drag-drop.css'}
    COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)
    DECLARATION_VALUE = re.compile(r'[\w-]+\s*:\s*([^;{}]+)[;}]')
    RAW_COLOR = re.compile(r'#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(')
    LEGACY_ALIAS = re.compile(
        r'--color-(?:bg-secondary|nav-links|text-normal|text-active|lines|lines-active|primary-active'
        r'|text-success|text-danger|button-text|button-text-hover|button-primary-text|danger-active)\b')

    def sloppy_labwork_stylesheets(self):
        for path in sorted(Path(settings.BASE_DIR).rglob('*.css')):
            relative_parts = path.relative_to(settings.BASE_DIR).parts
            if self.EXCLUDED_PARTS.isdisjoint(relative_parts) and path.name not in self.EXCLUDED_NAMES:
                yield path

    def declaration_values(self, path):
        css = self.COMMENT.sub('', path.read_text(encoding='utf-8'))
        return self.DECLARATION_VALUE.findall(css)

    def test_stylesheets_are_found(self):
        names = {path.name for path in self.sloppy_labwork_stylesheets()}
        self.assertIn('components.css', names)
        self.assertNotIn('tokens.css', names)

    def test_colors_come_from_tokens(self):
        for path in self.sloppy_labwork_stylesheets():
            raw_colors = [value.strip() for value in self.declaration_values(path) if self.RAW_COLOR.search(value)]
            self.assertEqual(raw_colors, [], f'{path.name} uses raw colors instead of tokens')

    def test_legacy_color_aliases_are_not_used(self):
        for path in self.sloppy_labwork_stylesheets():
            aliases = [value.strip() for value in self.declaration_values(path) if self.LEGACY_ALIAS.search(value)]
            self.assertEqual(aliases, [], f'{path.name} uses legacy color aliases')
