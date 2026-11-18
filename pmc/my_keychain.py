from collections import namedtuple
from datetime import date, datetime, time

from django.db.models import Count, Min, Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from .models import (
    Achievement, Badge, BoxLeagueSession, BoxMatch, Event, Feature, LadderChallenge, LeaderboardSeasonPeriod,
    PlayerRank, Playgroup, PlaygroupLeaderboard, Trophy, filter_upcoming_events,
)

MAX_ADDITIONAL_UP_NEXT_ITEMS = 3
RECENT_ACTIVITY_LIMIT = 3
PODIUM_PLACES = 3

UpNextItem = namedtuple('UpNextItem', [
    'title', 'detail', 'context', 'playgroup_name', 'url', 'action_label', 'due_on', 'event', 'is_registered'])
UpNext = namedtuple('UpNext', ['is_due', 'headline', 'additional_items'])
PlayerStats = namedtuple('PlayerStats', [
    'events_attended', 'events_won', 'podium_finishes', 'match_wins', 'win_rate', 'awards_earned',
    'match_record', 'best_finish', 'favorite_format', 'playing_since'])
ActivityRow = namedtuple('ActivityRow', ['result', 'playgroup_name', 'ranking_points', 'xp', 'has_record'])
PlaygroupRow = namedtuple('PlaygroupRow', ['playgroup', 'rank_this_month', 'is_global'])


def build_up_next(user):
    member_playgroups = list(Playgroup.objects.filter(members__user=user))
    owed_items = _owed_items(user, member_playgroups)
    member_playgroup_ids = {playgroup.pk for playgroup in member_playgroups}
    registered_event_items = _registered_event_items(user, member_playgroup_ids)
    if owed_items:
        return _up_next(True, owed_items + registered_event_items)
    if registered_event_items:
        return _up_next(False, registered_event_items)
    open_registration_item = _open_registration_item(user, member_playgroup_ids)
    if open_registration_item:
        return _up_next(False, [open_registration_item])
    return None


def build_player_stats(user, results):
    totals = results.aggregate(
        wins=Sum('num_wins'), losses=Sum('num_losses'), ties=Sum('num_ties'),
        playing_since=Min('event__start_date'))
    match_wins = totals['wins'] or 0
    match_losses = totals['losses'] or 0
    match_ties = totals['ties'] or 0
    matches_played = match_wins + match_losses + match_ties
    return PlayerStats(
        events_attended=results.count(),
        events_won=results.filter(finishing_position=1).count(),
        podium_finishes=results.filter(finishing_position__lte=PODIUM_PLACES).count(),
        match_wins=match_wins,
        win_rate=round(100 * match_wins / matches_played) if matches_played else None,
        awards_earned=_awards_earned(user),
        match_record=_match_record(match_wins, match_losses, match_ties) if matches_played else None,
        best_finish=results.filter(finishing_position__isnull=False).select_related('event').order_by(
            'finishing_position', '-event__start_date').first(),
        favorite_format=_favorite_format(results),
        playing_since=totals['playing_since'],
    )


def _match_record(wins, losses, ties):
    return f'{wins}–{losses}–{ties}' if ties else f'{wins}–{losses}'


def _favorite_format(results):
    most_played = results.filter(event__format__isnull=False).values('event__format__name').annotate(
        times_played=Count('pk')).order_by('-times_played', 'event__format__name').first()
    return most_played['event__format__name'] if most_played else None


def _awards_earned(user):
    return (
        Badge.with_user_badges(user).filter(user_badge_id__isnull=False).count()
        + Achievement.with_highest_user_achievements_tier(user).filter(user_achievement_tier__isnull=False).count()
        + Trophy.with_user_trophies(user).filter(user_trophy_amount__isnull=False).count()
    )


def build_recent_activity(user, results):
    member_playgroup_ids = set(Playgroup.objects.filter(members__user=user).values_list('pk', flat=True))
    recent_results = results.select_related('event').prefetch_related(
        'ranking_points', 'event__playgroups')[:RECENT_ACTIVITY_LIMIT]
    return [_activity_row(result, member_playgroup_ids) for result in recent_results]


def build_playgroup_rows(user):
    member_playgroups = list(
        Playgroup.objects.filter(members__user=user).annotate_next_upcoming_event().order_by('name'))
    global_playgroups = Playgroup.objects.filter(is_global=True).exclude(
        members__user=user).annotate_next_upcoming_event().order_by('name')
    rank_by_playgroup_id = _monthly_rank_by_playgroup_id(
        user, [playgroup.pk for playgroup in member_playgroups])
    return [
        PlaygroupRow(playgroup, rank_by_playgroup_id.get(playgroup.pk), playgroup.is_global)
        for playgroup in member_playgroups
    ] + [PlaygroupRow(playgroup, None, True) for playgroup in global_playgroups]


def _up_next(is_due, items):
    return UpNext(is_due, items[0], items[1:1 + MAX_ADDITIONAL_UP_NEXT_ITEMS])


def _owed_items(user, member_playgroups):
    enabled_feature_keys_by_playgroup_id = {
        playgroup.pk: playgroup.get_enabled_feature_keys() for playgroup in member_playgroups}
    ladder_playgroup_ids = _playgroup_ids_with(enabled_feature_keys_by_playgroup_id, Feature.Keys.LADDERS)
    box_league_playgroup_ids = _playgroup_ids_with(enabled_feature_keys_by_playgroup_id, Feature.Keys.BOX_LEAGUES)
    items_with_deadline = (
        _ladder_challenge_items(user, ladder_playgroup_ids)
        + _box_match_items(user, box_league_playgroup_ids)
    )
    return sorted(items_with_deadline, key=_deadline_sort_key) + _box_confirmation_items(
        user, box_league_playgroup_ids)


def _playgroup_ids_with(enabled_feature_keys_by_playgroup_id, feature_key):
    return [
        playgroup_id
        for playgroup_id, enabled_feature_keys in enabled_feature_keys_by_playgroup_id.items()
        if feature_key in enabled_feature_keys
    ]


def _deadline_sort_key(item):
    return (item.due_on is None, item.due_on or timezone.now())


def _involving(user):
    return Q(match__player_one__user=user) | Q(match__player_two__user=user)


def _opponent_of(user, match):
    return match.player_two if match.player_one.user_id == user.pk else match.player_one


def _short_date(value):
    return date_format(value, 'SHORT_DATE_FORMAT')


def _ladder_challenge_items(user, playgroup_ids):
    challenges = LadderChallenge.objects.filter(
        _involving(user),
        status=LadderChallenge.ChallengeStatuses.PENDING,
        respond_by__gte=timezone.now(),
        ladder__playgroup_id__in=playgroup_ids,
    ).select_related('ladder__playgroup', 'match__player_one__user', 'match__player_two__user')
    return [_ladder_challenge_item(user, challenge) for challenge in challenges]


def _ladder_challenge_item(user, challenge):
    ladder = challenge.ladder
    if challenge.defender.user_id == user.pk:
        title = _('%(name)s challenged you') % {'name': challenge.challenger}
    else:
        title = _('You challenged %(name)s') % {'name': challenge.defender}
    return UpNextItem(
        title=title,
        detail=_('on %(ladder)s. Record your result by %(date)s.') % {
            'ladder': ladder.name, 'date': _short_date(timezone.localtime(challenge.respond_by))},
        context=ladder.name,
        playgroup_name=ladder.playgroup.name,
        url=reverse('pmc-pg-ladder-challenge-result', kwargs={
            'slug': ladder.playgroup.slug, 'ladder_id': ladder.pk, 'challenge_id': challenge.pk}),
        action_label=_('Record Result'),
        due_on=challenge.respond_by,
        event=None,
        is_registered=False,
    )


def _box_match_items(user, playgroup_ids):
    box_matches = BoxMatch.objects.filter(
        _involving(user),
        box__session__status=BoxLeagueSession.SessionStatuses.ACTIVE,
        box__session__league__playgroup_id__in=playgroup_ids,
        match__result__isnull=True,
    ).select_related(
        'box__session__league__playgroup', 'match__player_one__user', 'match__player_two__user',
    ).order_by('pk')
    return [_box_match_item(user, box_match) for box_match in box_matches]


def _box_match_item(user, box_match):
    session = box_match.box.session
    league = session.league
    if session.ends_on:
        detail = _('in %(league)s. Record your result by %(date)s.') % {
            'league': league.name, 'date': _short_date(session.ends_on)}
    else:
        detail = _('in %(league)s. Record your result once you have played.') % {'league': league.name}
    return UpNextItem(
        title=_('Box match vs %(name)s') % {'name': _opponent_of(user, box_match.match)},
        detail=detail,
        context=league.name,
        playgroup_name=league.playgroup.name,
        url=reverse('pmc-pg-box-league-match-result', kwargs={
            'slug': league.playgroup.slug, 'league_id': league.pk, 'box_match_id': box_match.pk}),
        action_label=_('Record Result'),
        due_on=_end_of_day(session.ends_on),
        event=None,
        is_registered=False,
    )


def _end_of_day(day):
    if day is None:
        return None
    return timezone.make_aware(datetime.combine(day, time.max))


def _box_confirmation_items(user, playgroup_ids):
    proposals = BoxLeagueSession.objects.filter(
        status=BoxLeagueSession.SessionStatuses.PROPOSED,
        league__playgroup_id__in=playgroup_ids,
        league__roster__member__user=user,
    ).exclude(confirmations__member__user=user).select_related('league__playgroup').order_by('pk')
    return [_box_confirmation_item(proposal) for proposal in proposals]


def _box_confirmation_item(proposal):
    league = proposal.league
    return UpNextItem(
        title=league.name,
        detail=_('is planning its next session. Confirm that you are playing.'),
        context=_('Next session'),
        playgroup_name=league.playgroup.name,
        url=reverse('pmc-pg-box-league-session', kwargs={
            'slug': league.playgroup.slug, 'league_id': league.pk, 'number': proposal.number}),
        action_label=_('Review'),
        due_on=None,
        event=None,
        is_registered=False,
    )


def _upcoming_events():
    return filter_upcoming_events(Event.objects.all()).prefetch_related('playgroups').order_by('start_date', 'pk')


def _registered_event_items(user, member_playgroup_ids):
    return [
        _event_item(event, member_playgroup_ids, is_registered=True)
        for event in _upcoming_events().filter(results__user=user)
    ]


def _open_registration_item(user, member_playgroup_ids):
    event = _upcoming_events().filter(
        is_accepting_registrations=True,
        playgroups__in=member_playgroup_ids,
    ).exclude(results__user=user).distinct().first()
    return _event_item(event, member_playgroup_ids, is_registered=False) if event else None


def _playgroup_for_event(event, member_playgroup_ids):
    playgroups = list(event.playgroups.all())
    return next(
        (playgroup for playgroup in playgroups if playgroup.pk in member_playgroup_ids),
        playgroups[0] if playgroups else None,
    )


def _event_item(event, member_playgroup_ids, is_registered):
    playgroup = _playgroup_for_event(event, member_playgroup_ids)
    if is_registered:
        detail = _('is on %(date)s. You are registered.') % {'date': _short_date(event.start_date)}
    else:
        detail = _('is open for registration. It is on %(date)s.') % {'date': _short_date(event.start_date)}
    return UpNextItem(
        title=event.name,
        detail=detail,
        context=None,
        playgroup_name=playgroup.name if playgroup else None,
        url=_event_url(event, playgroup),
        action_label=_('View Event'),
        due_on=None,
        event=event,
        is_registered=is_registered,
    )


def _event_url(event, playgroup):
    if playgroup is None:
        return reverse('pmc-event-detail', kwargs={'pk': event.pk})
    return reverse('pmc-pg-event-detail', kwargs={'slug': playgroup.slug, 'pk': event.pk})


def _activity_row(result, member_playgroup_ids):
    playgroup = _playgroup_for_event(result.event, member_playgroup_ids)
    ranking_points = next(iter(result.ranking_points.all()), None)
    return ActivityRow(
        result=result,
        playgroup_name=playgroup.name if playgroup else None,
        ranking_points=ranking_points.points if ranking_points else None,
        xp=None if result.event.is_excluded_from_xp else result.get_xp() or None,
        has_record=any(
            count is not None for count in (result.num_wins, result.num_losses, result.num_ties)),
    )


def _monthly_rank_by_playgroup_id(user, playgroup_ids):
    monthly = LeaderboardSeasonPeriod.FrequencyOptions.MONTH
    hidden_leaderboards = set(PlaygroupLeaderboard.objects.filter(
        playgroup_id__in=playgroup_ids, is_leaderboard_hidden=True,
    ).values_list('playgroup_id', 'leaderboard_id'))
    ranks_this_month = PlayerRank.objects.filter(
        user=user,
        playgroup_id__in=playgroup_ids,
        leaderboard__period_frequency=monthly,
        period__frequency=monthly,
        period__start_date=date.today().replace(day=1),
    ).order_by('leaderboard__sort_order', 'leaderboard_id')
    rank_by_playgroup_id = {}
    for player_rank in ranks_this_month:
        if (player_rank.playgroup_id, player_rank.leaderboard_id) not in hidden_leaderboards:
            rank_by_playgroup_id.setdefault(player_rank.playgroup_id, player_rank.rank)
    return rank_by_playgroup_id
