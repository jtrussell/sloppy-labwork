"""
Project-wide context processors
"""
from django.conf import settings
from common.auth import is_teammate


def feature_flags(request):
    """ Some very simple feature flagging
    """
    return {
        'ft_use_posts': settings.FT_USE_POSTS,
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


NAV_SECTION_PATH_PREFIXES = (
    ('posts', ('/posts/',)),
    ('tourney', ('/tourney/',)),
    ('gizmos', ('/redacted/', '/timer/', '/lineups/', '/ghostform/', '/trade-secrets/')),
    ('profile', ('/@me/', '/accounts/')),
)


def nav_section(request):
    if request.path == '/':
        return {'nav_section': 'home'}
    for section, path_prefixes in NAV_SECTION_PATH_PREFIXES:
        if request.path.startswith(path_prefixes):
            return {'nav_section': section}
    return {'nav_section': None}
