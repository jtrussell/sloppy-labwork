"""
Project-wide context processors
"""

from django.conf import settings


def feature_flags(request):
    """ Some very simple feature flagging
    """
    return {
        'GA_TRACKING_ID': settings.GA_TRACKING_ID,
        'ft_use_register': settings.FT_USE_REGISTER,
        'ft_use_ratings': settings.FT_USE_RATINGS,
        'ft_use_posts': settings.FT_USE_POSTS,
    }
