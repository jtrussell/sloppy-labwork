from django import template
from datetime import date
from django.contrib.humanize.templatetags.humanize import naturalday
from django.utils.formats import date_format
from ..models import AchievementTier, PinnedAward
from django.utils.translation import gettext_lazy as _

register = template.Library()


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
