from django import template
from django.template.defaultfilters import stringfilter
import markdown as md
import re


register = template.Library()


@register.filter()
@stringfilter
def markdown(value):
    """
    Converts Markdown to HTML
    """
    return md.markdown(
        value,
        extensions=[
            'markdown.extensions.fenced_code',
            'markdown.extensions.toc',
            'markdown.extensions.attr_list',
        ],
        extension_configs={
            'markdown.extensions.toc': {
                'title': 'Contents',
            },
        }
    )


@register.filter()
@stringfilter
def squeeze(value):
    """
    Removes special characters and collapses whitespace
    """
    return re.sub(r'\W+', ' ', value)
