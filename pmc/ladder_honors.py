from collections import Counter, namedtuple

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

HONOR_WINDOW_DAYS = 30
RELENTLESS_CREEPER_MINIMUM_RANKS = 5
MADLAD_REQUIRED_TOP_SPOT_DEFENSES = 3

LadderHonor = namedtuple('LadderHonor', ['name', 'icon', 'detail'])
HonorExplanation = namedtuple('HonorExplanation', ['name', 'icon', 'explanation'])

HUNTER_OF_LEGEND = HonorExplanation(
    gettext_lazy('Hunter of Legend'), 'target',
    gettext_lazy('Most wins when challenging up in the last %(days)s days.') % {'days': HONOR_WINDOW_DAYS})
ARDENT_HERO = HonorExplanation(
    gettext_lazy('Ardent Hero'), 'shield-check',
    gettext_lazy('Most wins when defending a spot in the last %(days)s days.') % {'days': HONOR_WINDOW_DAYS})
RELENTLESS_CREEPER = HonorExplanation(
    gettext_lazy('Relentless Creeper'), 'stairs',
    gettext_lazy('Most ranks climbed in the last %(days)s days, with at least %(minimum)s.') % {
        'days': HONOR_WINDOW_DAYS, 'minimum': RELENTLESS_CREEPER_MINIMUM_RANKS})
MADLAD = HonorExplanation(
    gettext_lazy('Mad Mab'), 'flame',
    gettext_lazy('Defended #1 %(defenses)s times in a row, then dropped to the bottom to climb again.') % {
        'defenses': MADLAD_REQUIRED_TOP_SPOT_DEFENSES})

HONOR_EXPLANATIONS = (HUNTER_OF_LEGEND, ARDENT_HERO, RELENTLESS_CREEPER, MADLAD)


def honors_by_member_id(entries, challenges_resolved_in_window):
    joined_on_by_member_id = {entry.member_id: entry.joined_on for entry in entries}
    wins_challenging_up = Counter()
    wins_defending = Counter()
    ranks_climbed = Counter()
    for challenge in challenges_resolved_in_window:
        result = challenge.match.result
        winner_joined_on = joined_on_by_member_id.get(result.winner_id)
        if winner_joined_on is None or challenge.resolved_on < winner_joined_on:
            continue
        if result.winner_id == challenge.match.player_one_id:
            ranks_climbed[result.winner_id] += challenge.get_ranks_climbed()
            if not result.is_forfeit:
                wins_challenging_up[result.winner_id] += 1
        else:
            wins_defending[result.winner_id] += 1

    honors = {entry.member_id: [] for entry in entries}
    for member_id, wins in _leaders(wins_challenging_up, minimum=1).items():
        honors[member_id].append(LadderHonor(HUNTER_OF_LEGEND.name, HUNTER_OF_LEGEND.icon, ngettext(
            '%(count)s win challenging up in the last %(days)s days',
            '%(count)s wins challenging up in the last %(days)s days', wins) % {
                'count': wins, 'days': HONOR_WINDOW_DAYS}))
    for member_id, wins in _leaders(wins_defending, minimum=1).items():
        honors[member_id].append(LadderHonor(ARDENT_HERO.name, ARDENT_HERO.icon, ngettext(
            '%(count)s win defending a spot in the last %(days)s days',
            '%(count)s wins defending a spot in the last %(days)s days', wins) % {
                'count': wins, 'days': HONOR_WINDOW_DAYS}))
    for member_id, ranks in _leaders(ranks_climbed, minimum=RELENTLESS_CREEPER_MINIMUM_RANKS).items():
        honors[member_id].append(LadderHonor(RELENTLESS_CREEPER.name, RELENTLESS_CREEPER.icon, _(
            '%(count)s ranks climbed in the last %(days)s days') % {
                'count': ranks, 'days': HONOR_WINDOW_DAYS}))
    for entry in entries:
        if entry.madlad_count:
            honors[entry.member_id].append(LadderHonor(
                _('Mad Mab x%(count)s') % {'count': entry.madlad_count},
                MADLAD.icon,
                ngettext(
                    'Gave up the #1 spot to climb again %(count)s time',
                    'Gave up the #1 spot to climb again %(count)s times', entry.madlad_count) % {
                        'count': entry.madlad_count}))
    return honors


def _leaders(totals_by_member_id, minimum):
    highest_total = max(totals_by_member_id.values(), default=0)
    if highest_total < minimum:
        return {}
    return {member_id: total for member_id, total in totals_by_member_id.items() if total == highest_total}
