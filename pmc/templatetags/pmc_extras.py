from django import template
from ..models import AchievementTier
from django.utils.translation import gettext_lazy as _

register = template.Library()


@register.filter
def achievement_tier_label(value):
    try:
        return AchievementTier.TierOptions(value).label
    except ValueError:
        return _('N/A')
