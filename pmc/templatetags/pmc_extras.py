from django import template
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
