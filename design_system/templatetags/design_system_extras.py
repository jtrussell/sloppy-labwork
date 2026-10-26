import textwrap

from django import template
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from user_profile.models import UserProfile

register = template.Library()

EXAMPLE_FLAGS = {'themed', 'no_markup'}


class ExampleNode(template.Node):
    def __init__(self, nodelist, is_themed, shows_markup):
        self.nodelist = nodelist
        self.is_themed = is_themed
        self.shows_markup = shows_markup

    def render(self, context):
        rendered_example = self.nodelist.render(context)
        return render_to_string('design_system/partials/example.html', {
            'preview': mark_safe(rendered_example),
            'markup': textwrap.dedent(rendered_example).strip(),
            'themes': UserProfile.ThemeOptions.choices if self.is_themed else (),
            'shows_markup': self.shows_markup,
        })


@register.tag(name='ds_example')
def ds_example(parser, token):
    flags = token.split_contents()[1:]
    unknown_flags = set(flags) - EXAMPLE_FLAGS
    if unknown_flags:
        raise template.TemplateSyntaxError(f'ds_example got unknown flags: {", ".join(sorted(unknown_flags))}')
    nodelist = parser.parse(('end_ds_example',))
    parser.delete_first_token()
    return ExampleNode(nodelist, is_themed='themed' in flags, shows_markup='no_markup' not in flags)


@register.filter
def token_reference(token_name):
    return f'var({token_name})'


@register.filter
def lookup(mapping, key):
    return mapping.get(key)


@register.filter
def split(value):
    return value.split()


@register.filter
def form_level_errors(form):
    hidden_field_errors = [
        f'(Hidden field {field.name}) {error}' for field in form.hidden_fields() for error in field.errors
    ]
    return [*form.non_field_errors(), *hidden_field_errors]


@register.simple_tag(takes_context=True)
def preserved_query(context, page_param='page'):
    request = context.get('request')
    if request is None:
        return ''
    query = request.GET.copy()
    query.pop(page_param, None)
    encoded_query = query.urlencode()
    return f'&{encoded_query}' if encoded_query else ''
