import re
import textwrap

import markdown
import nh3
from django import template
from datetime import date
from django.contrib.humanize.templatetags.humanize import naturalday
from django.template.defaultfilters import stringfilter
from django.template.loader import render_to_string
from django.utils.formats import date_format
from django.utils.safestring import mark_safe
from ..models import AchievementTier, PinnedAward
from django.utils.translation import gettext_lazy as _

register = template.Library()

MARKDOWN_EXTENSIONS = [
    'markdown.extensions.fenced_code',
    'markdown.extensions.toc',
    'markdown.extensions.attr_list',
]
MARKDOWN_EXTENSION_CONFIGS = {'markdown.extensions.toc': {'title': 'Contents'}}
EMBEDDABLE_IFRAME_SOURCE_PREFIXES = (
    'https://www.google.com/maps/embed?',
    'https://www.google.com/maps/d/embed?',
)
SANITIZED_MARKDOWN_TAGS = nh3.ALLOWED_TAGS | {'iframe'}
SANITIZED_MARKDOWN_ATTRIBUTES = {
    **nh3.ALLOWED_ATTRIBUTES,
    'code': {'class'},
    **{heading: {'id'} for heading in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')},
    'iframe': {'src', 'width', 'height', 'title', 'loading', 'allowfullscreen', 'referrerpolicy'},
}


IFRAME_WITHOUT_SOURCE = re.compile(r'<iframe(?![^>]*\ssrc=)[^>]*>.*?</iframe>', re.S)


def keep_only_embeddable_iframe_sources(tag, attribute, value):
    if tag == 'iframe' and attribute == 'src' and not value.startswith(EMBEDDABLE_IFRAME_SOURCE_PREFIXES):
        return None
    return value


@register.filter
@stringfilter
def markdown_sanitized(value):
    rendered_html = markdown.markdown(
        value, extensions=MARKDOWN_EXTENSIONS, extension_configs=MARKDOWN_EXTENSION_CONFIGS)
    sanitized_html = nh3.clean(
        rendered_html,
        tags=SANITIZED_MARKDOWN_TAGS,
        attributes=SANITIZED_MARKDOWN_ATTRIBUTES,
        attribute_filter=keep_only_embeddable_iframe_sources,
    )
    return mark_safe(IFRAME_WITHOUT_SOURCE.sub('', sanitized_html))


@register.filter
def achievement_tier_label(value):
    try:
        return AchievementTier.TierOptions(value).label
    except ValueError:
        return _('N/A')


@register.simple_tag
def pinned_pk(pinned_map, award_type, award_id):
    return pinned_map.get((award_type, award_id))


@register.simple_tag
def award_type_badge():
    return PinnedAward.AwardTypeOptions.BADGE


@register.simple_tag
def award_type_achievement():
    return PinnedAward.AwardTypeOptions.ACHIEVEMENT


@register.simple_tag
def award_type_trophy():
    return PinnedAward.AwardTypeOptions.TROPHY


UPCOMING_DAYS_SHOWN_AS_COUNT = range(2, 7)


@register.filter
def relative_event_day(value):
    if not value:
        return ''
    days_until = (value - date.today()).days
    if days_until in UPCOMING_DAYS_SHOWN_AS_COUNT:
        return _('in %(days)d days') % {'days': days_until}
    if days_until in (0, 1):
        return naturalday(value)
    return date_format(value, 'D, M j')


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


@register.filter
def token_reference(token_name):
    return f'var({token_name})'


GALLERY_EXAMPLE_FLAGS = {'themed', 'no_markup'}


class GalleryExampleNode(template.Node):
    def __init__(self, nodelist, is_themed, shows_markup):
        self.nodelist = nodelist
        self.is_themed = is_themed
        self.shows_markup = shows_markup

    def render(self, context):
        rendered_example = self.nodelist.render(context)
        return render_to_string('pmc/_ds-example.html', {
            'preview': mark_safe(rendered_example),
            'markup': textwrap.dedent(rendered_example).strip(),
            'themes': context.get('themes', ()) if self.is_themed else (),
            'shows_markup': self.shows_markup,
        })


@register.tag(name='kc_example')
def kc_example(parser, token):
    flags = token.split_contents()[1:]
    unknown_flags = set(flags) - GALLERY_EXAMPLE_FLAGS
    if unknown_flags:
        raise template.TemplateSyntaxError(f'kc_example got unknown flags: {", ".join(sorted(unknown_flags))}')
    nodelist = parser.parse(('end_kc_example',))
    parser.delete_first_token()
    return GalleryExampleNode(nodelist, is_themed='themed' in flags, shows_markup='no_markup' not in flags)
