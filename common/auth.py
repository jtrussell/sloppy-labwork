from functools import wraps

from django.core.exceptions import PermissionDenied

from common.social_accounts import get_discord_data

_TEAMMATE_DISCORD_IDS = {
    '600412900259266590',  # jtrussell
    '752812884559396885',  # kveld
    '547135519394365442',  # quickdraw3457
    '403203872757252126',  # bhawk
    '281128837549391882',  # crusader
    '689961402072432732',  # jdg314
    '558705856019955713',  # not2night
    '405869761902149633',  # nowinstereo
    '577478847243747338',  # strussell
}


def is_teammate(user):
    if not user.is_authenticated:
        return False
    discord_data = get_discord_data(user)
    return discord_data.get('id') in _TEAMMATE_DISCORD_IDS


def teammate_required(view):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            if not user.is_superuser and not is_teammate(user):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator(view)
