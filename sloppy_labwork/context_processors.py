"""
Project-wide context processors
"""

from django.conf import settings

from common.auth import is_teammate


def feature_flags(request):
    """ Some very simple feature flagging
    """
    return {
        'GA_TRACKING_ID': settings.GA_TRACKING_ID,
        'ft_use_register': settings.FT_USE_REGISTER,
        'ft_use_ratings': settings.FT_USE_RATINGS,
        'ft_use_posts': settings.FT_USE_POSTS,
        'ft_use_events': settings.FT_USE_EVENTS,
    }


def teammate_authorized(request):
    """
      For showing parts of website to teammate users
    """
    return {
        'teammate_authorized': is_teammate(request.user)
    }
