"""
Project-wide context processors
"""
from django.conf import settings
from common.auth import is_teammate


def feature_flags(request):
    """ Some very simple feature flagging
    """
    return {
        'ft_use_register': settings.FT_USE_REGISTER,
        'ft_use_ratings': settings.FT_USE_RATINGS,
        'ft_use_posts': settings.FT_USE_POSTS,
        'ft_use_events': settings.FT_USE_EVENTS,
        'ft_use_tourneys': settings.FT_USE_TOURNEYS,
    }


def teammate_authorized(request):
    """
      For showing parts of website to teammate users
    """
    return {
        'teammate_authorized': is_teammate(request.user)
    }


def base_template(request):
    if request.host.name == 'keychain':
        base_template = 'pmc/_base.html'
    else:
        base_template = 'page.html'

    return {
        'base_template': base_template
    }
