from django import template
from django.template.defaultfilters import stringfilter


register = template.Library()


@register.filter()
@stringfilter
def obfuscate(value):
    """
    Replaces all but first and last chars of a string with stars
    """
    return value[0] + ('*' * (len(value) - 2)) + value[-1]