from http import HTTPStatus
import json
import os
import csv
from datetime import date
from datetime import timedelta
from django.core.mail import send_mail
from django.conf import settings
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Sum, Count, Q, Prefetch
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.views import generic
from django.template import loader
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.contrib.auth.mixins import LoginRequiredMixin
from pmc.context_processors import playgroup
from pmc.forms import EventForm, EventResultDeckForm, EventUpdateForm, LeaderboardSeasonPeriodForm, PlaygroupForm, PlaygroupJoinRequestForm, PmcProfileForm, PmcProfilePrivacyForm, RankingPointsMapVersionForm, VenueForm
from pmc.forms import PlaygroupMemberForm
from pmc.forms import LadderForm, LadderAddMemberForm, LadderMoveMemberForm, MatchOutcomeForm
from pmc.forms import LadderPlayedResultForm
from pmc.ladder_notifications import send_test_message as send_ladder_test_message
from pmc.forms import BoxLeagueForm, BoxLeagueTierNameFormSet, BoxLeagueAddMemberForm
from pmc.forms import BoxAssignmentForm, BoxSessionStartForm, BoxProposalResizeForm, BoxAddForm
from user_profile.forms import EditUsernameForm
from .models import AchievementTier, AwardBase, Badge, EventResult, EventResultDeck, LeaderboardLog, LeaderboardSeasonPeriod, PlaygroupJoinRequest, PinnedAward, UserAchievementTier, UserBadge, Trophy, UserTrophy, Achievement
from .models import PlayerRank
from .models import Leaderboard
from .models import Playgroup
from .models import PlaygroupEvent
from .models import PlaygroupMember
from .models import Event
from .models import RankingPointsService
from .models import Avatar
from .models import AvatarCategory
from .models import Background
from .models import BackgroundCategory
from .models import RankingPointsMap, RankingPointsMapVersion
from .models import AwardAssignmentService
from .models import Venue, PlaygroupVenue, PlaygroupType, EventFormat, PlaygroupQuerySet
from .models import exclude_upcoming_event_results
from .models import filter_upcoming_events, get_activity_level
from .models import Ladder, LadderChallenge, LadderRuleViolation
from .models import Feature
from .models import Box, BoxLeague, BoxLeagueSession, BoxLeagueRuleViolation, BoxMatch


def is_pg_member(view):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            playgroup = Playgroup.objects.filter(slug=kwargs['slug']).first()
            if playgroup and playgroup.is_global:
                return view_func(request, *args, **kwargs)

            is_member = PlaygroupMember.objects.filter(
                user=request.user, playgroup__slug=kwargs['slug']).exists()
            if is_member:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return wrapper
    return decorator(view)


def is_pg_staff(view):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            is_member = PlaygroupMember.objects.filter(
                user=request.user, playgroup__slug=kwargs['slug'], is_staff=True).exists()
            if is_member:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return wrapper
    return decorator(view)


def requires_pg_feature(feature_key):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            playgroup = get_object_or_404(Playgroup, slug=kwargs['slug'])
            if not playgroup.has_feature(feature_key):
                return redirect_to(request, reverse('pmc-pg-detail', kwargs={'slug': playgroup.slug}))
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def api_key_required(view):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            api_key = request.META.get('HTTP_X_API_KEY')
            if api_key == os.environ['PMC_RATINGS_API_KEY']:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return wrapper
    return decorator(view)


def main_site_url(request, path):
    host = request.get_host()
    if host.startswith('keychain.'):
        host = host[len('keychain.'):]
    scheme = 'https' if request.is_secure() else 'http'
    return f'{scheme}://{host}{path}'


def redirect_to(request, url):
    """Redirect to a URL, using HTMX if available."""
    if request.htmx:
        resp = HttpResponse(url)
        resp['HX-Redirect'] = url
        return resp
    return HttpResponseRedirect(url)


class PlaygroupDetail(generic.DetailView):
    model = Playgroup
    template_name = 'pmc/playgroup-detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cutoff = date.today() - timedelta(days=1)
        upcoming_events = Event.objects.filter(
            playgroups=self.object,
            start_date__gte=cutoff,
        ).exclude(
            results__finishing_position__isnull=False,
        ).order_by('start_date')
        context['upcoming_events'] = upcoming_events
        is_member = self.request.user.is_authenticated and self.object.members.filter(
            user=self.request.user).exists()
        enabled_feature_keys = self.object.get_enabled_feature_keys()
        if is_member and not self.object.is_global and Feature.Keys.LADDERS in enabled_feature_keys:
            context['ladders'] = self.object.ladders.annotate(
                num_players=Count('entries'))
        if is_member and not self.object.is_global and Feature.Keys.BOX_LEAGUES in enabled_feature_keys:
            context['box_leagues'] = self.object.box_leagues.annotate(
                num_players=Count('roster'))
        return context


@login_required
def playgroup_join_request(request, slug):
    existing_membership = PlaygroupMember.objects.filter(
        playgroup__slug=slug, user=request.user).first()

    if existing_membership:
        messages.error(request, _(
            'You are already a member of this playgroup.'))
        return HttpResponseRedirect(reverse('pmc-pg-detail', kwargs={'slug': slug}))

    form = PlaygroupJoinRequestForm(request.POST or None)
    existing_request = PlaygroupJoinRequest.objects.filter(
        playgroup__slug=slug,
        user=request.user,
        status=PlaygroupJoinRequest.RequestStatuses.SUBMITTED
    ).first()

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            if existing_request:
                existing_request.status = PlaygroupJoinRequest.RequestStatuses.CANCELLED
                existing_request.save()
                messages.success(request, _('Join request cancelled.'))
                return HttpResponseRedirect(reverse('pmc-pg-join', kwargs={'slug': slug}))
        else:
            if form.is_valid():
                playgroup = Playgroup.objects.get(slug=slug)
                playgroup_join_request = form.save(commit=False)
                playgroup_join_request.playgroup = playgroup
                playgroup_join_request.user = request.user
                playgroup_join_request.save()

                send_mail(
                    subject=_('New join request for {}').format(
                        playgroup.name),
                    message='You have received a new join request on KeyChain! Please log in to accept or reject this request.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=playgroup.get_staff_email_list(),
                    fail_silently=True,
                    html_message=loader.render_to_string(
                        'pmc/email-playgroup-join-request.html',
                        {'request': request, 'join_request': playgroup_join_request}
                    )
                )
                messages.success(request, _('Join request submitted.'))
                return HttpResponseRedirect(reverse('pmc-pg-join', kwargs={'slug': slug}))
    context = {'form': form, 'existing_request': existing_request}
    return render(request, 'pmc/pg-playgroup-join-request.html', context)


@login_required
@is_pg_staff
def playgroup_join_request_manage(request, slug, pk):
    join_request = get_object_or_404(
        PlaygroupJoinRequest, pk=pk, playgroup__slug=slug)

    if join_request.status != PlaygroupJoinRequest.RequestStatuses.SUBMITTED:
        messages.success(request, _(
            'This join request has already been handled.'))
        return HttpResponseRedirect(reverse('pmc-pg-manage', kwargs={
            'slug': slug,
        }))

    if request.method == 'POST':
        if request.POST.get('action') == 'accept':
            join_request.status = PlaygroupJoinRequest.RequestStatuses.ACCEPTED
            join_request.save()
            PlaygroupMember.objects.create(
                playgroup=join_request.playgroup,
                user=join_request.user,
                is_staff=False
            )
            messages.success(request, _('Join request accepted.'))

            send_mail(
                subject=_('Join request accepted for {}').format(
                    join_request.playgroup.name),
                message='You have been accepted into the playgroup {}!'.format(
                    join_request.playgroup.name),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[join_request.user.email],
                fail_silently=True,
                html_message=loader.render_to_string(
                    'pmc/email-playgroup-join-request-accepted.html',
                    {'request': request, 'join_request': join_request}
                )
            )

        elif request.POST.get('action') == 'decline':
            join_request.status = PlaygroupJoinRequest.RequestStatuses.DECLINED
            join_request.save()
            messages.success(request, _('Join request declined.'))

        return HttpResponseRedirect(reverse('pmc-pg-manage', kwargs={
            'slug': slug,
        }))

    context = {'join_request': join_request}
    return render(request, 'pmc/pg-join-request-manage.html', context)


@login_required
@is_pg_staff
def manage_playgroup(request, slug):
    playgroup = get_object_or_404(Playgroup, slug=slug)
    if request.method == 'POST':
        form = PlaygroupForm(request.POST, instance=playgroup)
        if form.is_valid():
            pg = form.save()
            return HttpResponseRedirect(reverse('pmc-pg-detail', kwargs={'slug': pg.slug}))
    else:
        form = PlaygroupForm(instance=playgroup)

    context = {
        'form': form,
        'join_requests': PlaygroupJoinRequest.objects.filter(
            playgroup=playgroup,
            status=PlaygroupJoinRequest.RequestStatuses.SUBMITTED
        ),
        'venues': playgroup.venues.all(),
    }
    return render(request, 'pmc/pg-manage.html', context)


@login_required
@is_pg_staff
def add_playgroup_venue(request, slug):
    from django.utils.text import slugify
    playgroup = get_object_or_404(Playgroup, slug=slug)
    if request.method == 'POST':
        form = VenueForm(request.POST)
        if form.is_valid():
            venue = form.save(commit=False)
            venue.created_by = request.user
            base_slug = slugify(venue.name)[:100]
            venue.slug = base_slug
            counter = 1
            while Venue.objects.filter(slug=venue.slug).exists():
                venue.slug = f"{base_slug}-{counter}"[:100]
                counter += 1
            venue.save()
            if venue.geocode():
                messages.success(request, _(
                    'Venue added and address geocoded.'))
            else:
                messages.warning(request, _(
                    'Venue added but address could not be geocoded. You may need to update the address.'))
            PlaygroupVenue.objects.create(
                playgroup=playgroup,
                venue=venue,
                added_by=request.user
            )
            return HttpResponseRedirect(reverse('pmc-pg-manage', kwargs={'slug': slug}))
    else:
        form = VenueForm()

    return render(request, 'pmc/pg-venue-add.html', {'form': form})


@login_required
@is_pg_staff
def remove_playgroup_venue(request, slug, venue_id):
    playgroup = get_object_or_404(Playgroup, slug=slug)
    venue = get_object_or_404(Venue, pk=venue_id)
    PlaygroupVenue.objects.filter(playgroup=playgroup, venue=venue).delete()
    if playgroup.primary_venue == venue:
        playgroup.primary_venue = None
        playgroup.save()
    playgroup.refresh_from_db()
    messages.success(request, _('Venue removed.'))
    if request.htmx:
        return render(request, 'pmc/pg-manage.html#venues-list', {
            'playgroup': playgroup,
            'venues': playgroup.venues.all(),
        })
    return redirect_to(request, reverse('pmc-pg-manage', kwargs={'slug': slug}))


@login_required
@is_pg_staff
def set_playgroup_primary_venue(request, slug):
    playgroup = get_object_or_404(Playgroup, slug=slug)
    venue_id = request.POST.get('venue_id')
    if venue_id:
        venue = get_object_or_404(Venue, pk=venue_id)
        if playgroup.venues.filter(pk=venue.pk).exists():
            playgroup.primary_venue = venue
            playgroup.save()
            messages.success(request, _('Primary venue updated.'))
    else:
        playgroup.primary_venue = None
        playgroup.save()
        messages.success(request, _('Primary venue cleared.'))
    playgroup.refresh_from_db()
    if request.htmx:
        return render(request, 'pmc/pg-manage.html#venues-list', {
            'playgroup': playgroup,
            'venues': playgroup.venues.all(),
        })
    return redirect_to(request, reverse('pmc-pg-manage', kwargs={'slug': slug}))


def get_ladder_or_404(slug, ladder_id):
    return get_object_or_404(
        Ladder.objects.select_related('playgroup'),
        pk=ladder_id, playgroup__slug=slug, playgroup__is_global=False)


def get_ladder_challenge_or_404(ladder, challenge_id):
    return get_object_or_404(
        LadderChallenge.objects.select_related(
            'match__player_one__user', 'match__player_two__user'),
        pk=challenge_id, ladder=ladder)


def get_viewer_member_or_403(request, playgroup):
    member = PlaygroupMember.objects.filter(
        playgroup=playgroup, user=request.user).first()
    if member is None:
        raise PermissionDenied
    return member


def ladder_detail_url(ladder):
    return reverse('pmc-pg-ladder-detail', kwargs={'slug': ladder.playgroup.slug, 'ladder_id': ladder.pk})


def ladder_manage_url(ladder):
    return reverse('pmc-pg-ladder-manage', kwargs={'slug': ladder.playgroup.slug, 'ladder_id': ladder.pk})


def run_competition_action(request, action, success_message, redirect_url):
    try:
        action()
    except (LadderRuleViolation, BoxLeagueRuleViolation) as violation:
        messages.error(request, str(violation))
    else:
        messages.success(request, success_message)
    return redirect_to(request, redirect_url)


def report_invalid_form(request, form):
    for errors in form.errors.values():
        for error in errors:
            messages.error(request, error)


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@is_pg_member
def playgroup_ladders(request, slug):
    playgroup = get_object_or_404(Playgroup, slug=slug, is_global=False)
    return render(request, 'pmc/pg-ladders.html', {
        'ladders': playgroup.ladders.annotate(num_players=Count('entries')),
    })


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@is_pg_staff
def create_playgroup_ladder(request, slug):
    playgroup = get_object_or_404(Playgroup, slug=slug, is_global=False)
    form = LadderForm(request.POST or None, playgroup=playgroup)
    if request.method == 'POST' and form.is_valid():
        ladder = form.save(commit=False)
        ladder.playgroup = playgroup
        ladder.created_by = request.user
        ladder.save()
        messages.success(request, _('Ladder created.'))
        return HttpResponseRedirect(ladder_manage_url(ladder))
    return render(request, 'pmc/pg-ladder-form.html', {'form': form})


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@is_pg_staff
def edit_playgroup_ladder(request, slug, ladder_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    form = LadderForm(request.POST or None, instance=ladder,
                      playgroup=ladder.playgroup)
    if request.method == 'POST' and form.is_valid():
        ladder = form.save()
        if 'challenges_enabled' in form.changed_data and not ladder.challenges_enabled:
            ladder.void_open_challenges()
        messages.success(request, _('Ladder settings saved.'))
        return HttpResponseRedirect(ladder_manage_url(ladder))
    return render(request, 'pmc/pg-ladder-form.html', {
        'form': form,
        'ladder': ladder,
        'active_tab': 'settings',
    })


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@is_pg_member
def playgroup_ladder_detail(request, slug, ladder_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    ladder.resolve_overdue_challenges()
    viewer_member = PlaygroupMember.objects.filter(
        playgroup=ladder.playgroup, user=request.user).first()
    standings = ladder.get_standings_for(viewer_member)
    viewer_standing = next(
        (standing for standing in standings if standing.is_viewer), None)
    open_challenges = list(ladder.get_open_challenges())
    viewer_challenges = [
        challenge for challenge in open_challenges
        if viewer_member and challenge.match.involves(viewer_member)
    ]
    challengeable_standings = [standing for standing in standings if standing.can_be_challenged]
    return render(request, 'pmc/pg-ladder-detail.html', {
        'ladder': ladder,
        'standings': standings,
        'viewer_standing': viewer_standing,
        'viewer_entry': viewer_standing.entry if viewer_standing else None,
        'viewer_challenge': viewer_challenges[0] if viewer_challenges else None,
        'challengeable_standings': challengeable_standings,
        'challenge_block_reason': next(
            (standing.challenge_block_reason for standing in standings if standing.challenge_block_reason), None),
        'open_challenges': open_challenges,
        'recent_results': ladder.get_recent_results(),
    })


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@is_pg_member
def record_played_ladder_result(request, slug, ladder_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    viewer_member = get_viewer_member_or_403(request, ladder.playgroup)
    if not ladder.entries.filter(member=viewer_member).exists() or not ladder.challenges_enabled:
        messages.error(request, _('Join this ladder to record games, and make sure challenges are enabled.'))
        return HttpResponseRedirect(ladder_detail_url(ladder))
    form = LadderPlayedResultForm(request.POST or None, ladder=ladder, member=viewer_member)
    if request.method == 'POST' and form.is_valid():
        return run_competition_action(
            request,
            lambda: ladder.record_played_result(
                viewer_member, form.cleaned_data['opponent'], form.get_winner(), request.user),
            _('Result recorded.'),
            ladder_detail_url(ladder),
        )
    return render(request, 'pmc/pg-ladder-played-result.html', {
        'ladder': ladder,
        'form': form,
    })


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@require_POST
@is_pg_member
def update_ladder_challenge_emails(request, slug, ladder_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    viewer_member = get_viewer_member_or_403(request, ladder.playgroup)
    entry = get_object_or_404(ladder.entries, member=viewer_member)
    entry.email_on_challenge = request.POST.get('email_on_challenge') == 'on'
    entry.save(update_fields=['email_on_challenge'])
    if entry.email_on_challenge:
        messages.success(request, _('We will email you when someone challenges you on this ladder.'))
    else:
        messages.success(request, _('Challenge emails turned off for this ladder.'))
    if request.htmx:
        return HttpResponse(status=HTTPStatus.NO_CONTENT)
    return HttpResponseRedirect(ladder_detail_url(ladder))


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@require_POST
@is_pg_staff
def test_ladder_discord_webhook(request, slug, ladder_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    if not ladder.discord_webhook_url:
        messages.error(request, _('Add a Discord webhook URL first.'))
    else:
        was_sent, problem = send_ladder_test_message(ladder)
        if was_sent:
            messages.success(request, _('Test message sent to Discord.'))
        else:
            messages.error(request, problem)
    return redirect_to(request, reverse(
        'pmc-pg-ladder-edit', kwargs={'slug': slug, 'ladder_id': ladder.pk}))


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@is_pg_staff
def manage_playgroup_ladder(request, slug, ladder_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    ladder.resolve_overdue_challenges()
    return render(request, 'pmc/pg-ladder-manage.html', {
        'ladder': ladder,
        'active_tab': 'challenges' if request.GET.get('tab') == 'challenges' else 'roster',
        'standings': ladder.get_standings_for(None),
        'add_member_form': LadderAddMemberForm(ladder=ladder),
        'open_challenges': ladder.get_open_challenges(),
        'recent_results': ladder.get_recent_results(),
    })


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@require_POST
@is_pg_member
def join_playgroup_ladder(request, slug, ladder_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    viewer_member = get_viewer_member_or_403(request, ladder.playgroup)
    return run_competition_action(
        request,
        lambda: ladder.add_member(viewer_member),
        _('Welcome to the ladder!'),
        ladder_detail_url(ladder),
    )


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@require_POST
@is_pg_member
def leave_playgroup_ladder(request, slug, ladder_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    viewer_member = get_viewer_member_or_403(request, ladder.playgroup)
    return run_competition_action(
        request,
        lambda: ladder.remove_member(viewer_member),
        _('You have left the ladder.'),
        ladder_detail_url(ladder),
    )


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@require_POST
@is_pg_member
def issue_ladder_challenge(request, slug, ladder_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    viewer_member = get_viewer_member_or_403(request, ladder.playgroup)
    defender_id = request.POST.get('defender_id', '')
    if not defender_id.isdigit():
        raise Http404
    defender = get_object_or_404(
        PlaygroupMember, pk=defender_id, playgroup=ladder.playgroup)
    return run_competition_action(
        request,
        lambda: ladder.issue_challenge(viewer_member, defender),
        _('Challenge issued to %(name)s.') % {'name': defender},
        ladder_detail_url(ladder),
    )


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@is_pg_member
def record_ladder_challenge_result(request, slug, ladder_id, challenge_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    ladder.resolve_overdue_challenges()
    challenge = get_ladder_challenge_or_404(ladder, challenge_id)
    is_participant = request.user.pk in (
        challenge.match.player_one.user_id, challenge.match.player_two.user_id)
    if not is_participant and not ladder.is_organizer(request.user):
        raise PermissionDenied
    if challenge.status == LadderChallenge.ChallengeStatuses.FORFEITED:
        messages.error(request, _(
            'The response window has passed, so the challenger won by forfeit.'))
        return HttpResponseRedirect(ladder_detail_url(ladder))
    if not challenge.is_pending():
        messages.error(request, _('This challenge has already been resolved.'))
        return HttpResponseRedirect(ladder_detail_url(ladder))

    form = MatchOutcomeForm(
        request.POST or None,
        match=challenge.match,
        player_one_won_label=_('%(name)s won and moves ahead'),
    )
    if request.method == 'POST' and form.is_valid():
        return run_competition_action(
            request,
            lambda: ladder.record_result(
                challenge, form.get_winner(), request.user),
            _('Result recorded.'),
            ladder_detail_url(ladder),
        )
    return render(request, 'pmc/pg-ladder-challenge-result.html', {
        'ladder': ladder,
        'challenge': challenge,
        'form': form,
    })


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@require_POST
@is_pg_member
def withdraw_ladder_challenge(request, slug, ladder_id, challenge_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    challenge = get_ladder_challenge_or_404(ladder, challenge_id)
    return run_competition_action(
        request,
        lambda: ladder.withdraw_challenge(challenge, request.user),
        _('Challenge withdrawn.'),
        ladder_detail_url(ladder),
    )


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@require_POST
@is_pg_staff
def void_ladder_challenge(request, slug, ladder_id, challenge_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    challenge = get_ladder_challenge_or_404(ladder, challenge_id)
    return run_competition_action(
        request,
        lambda: ladder.void_challenge(challenge, request.user),
        _('Challenge voided. Positions were not changed; use Move to correct them if needed.'),
        f'{ladder_manage_url(ladder)}?tab=challenges',
    )


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@require_POST
@is_pg_staff
def add_ladder_member(request, slug, ladder_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    form = LadderAddMemberForm(request.POST, ladder=ladder)
    if not form.is_valid():
        report_invalid_form(request, form)
        return redirect_to(request, ladder_manage_url(ladder))
    member = form.cleaned_data['member']
    return run_competition_action(
        request,
        lambda: ladder.add_member(member, form.cleaned_data['position']),
        _('%(name)s added to the ladder.') % {'name': member},
        ladder_manage_url(ladder),
    )


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@require_POST
@is_pg_staff
def move_ladder_member(request, slug, ladder_id, member_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    member = get_object_or_404(
        PlaygroupMember, pk=member_id, playgroup=ladder.playgroup)
    form = LadderMoveMemberForm(request.POST)
    if not form.is_valid():
        report_invalid_form(request, form)
        return redirect_to(request, ladder_manage_url(ladder))
    return run_competition_action(
        request,
        lambda: ladder.move_member(member, form.cleaned_data['position']),
        _('%(name)s moved.') % {'name': member},
        ladder_manage_url(ladder),
    )


@login_required
@requires_pg_feature(Feature.Keys.LADDERS)
@require_POST
@is_pg_staff
def remove_ladder_member(request, slug, ladder_id, member_id):
    ladder = get_ladder_or_404(slug, ladder_id)
    member = get_object_or_404(
        PlaygroupMember, pk=member_id, playgroup=ladder.playgroup)
    return run_competition_action(
        request,
        lambda: ladder.remove_member(member),
        _('%(name)s removed from the ladder.') % {'name': member},
        ladder_manage_url(ladder),
    )


@login_required
@is_pg_member
def playgroup_play(request, slug):
    playgroup = get_object_or_404(Playgroup, slug=slug, is_global=False)
    enabled_feature_keys = playgroup.get_enabled_feature_keys()
    has_ladders = Feature.Keys.LADDERS in enabled_feature_keys
    has_box_leagues = Feature.Keys.BOX_LEAGUES in enabled_feature_keys
    if not has_ladders and not has_box_leagues:
        return redirect_to(request, reverse('pmc-pg-detail', kwargs={'slug': slug}))
    return render(request, 'pmc/pg-play.html', {
        'ladders': playgroup.ladders.annotate(num_players=Count('entries')) if has_ladders else None,
        'box_leagues': playgroup.box_leagues.annotate(num_players=Count('roster')) if has_box_leagues else None,
    })


def get_box_league_or_404(slug, league_id):
    return get_object_or_404(
        BoxLeague.objects.select_related('playgroup'),
        pk=league_id, playgroup__slug=slug, playgroup__is_global=False)


def get_box_league_session_or_404(league, number):
    return get_object_or_404(BoxLeagueSession, league=league, number=number)


def get_box_match_or_404(league, box_match_id):
    return get_object_or_404(
        BoxMatch.objects.select_related(
            'box__session', 'match__player_one__user', 'match__player_two__user', 'match__result'),
        pk=box_match_id, box__session__league=league)


def box_league_url(league, name='pmc-pg-box-league-detail'):
    return reverse(name, kwargs={'slug': league.playgroup.slug, 'league_id': league.pk})


def box_league_session_url(session):
    return reverse('pmc-pg-box-league-session', kwargs={
        'slug': session.league.playgroup.slug,
        'league_id': session.league_id,
        'number': session.number,
    })


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@is_pg_member
def playgroup_box_leagues(request, slug):
    playgroup = get_object_or_404(Playgroup, slug=slug, is_global=False)
    return render(request, 'pmc/pg-box-leagues.html', {
        'box_leagues': playgroup.box_leagues.annotate(num_players=Count('roster')),
    })


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@is_pg_staff
def create_playgroup_box_league(request, slug):
    playgroup = get_object_or_404(Playgroup, slug=slug, is_global=False)
    form = BoxLeagueForm(request.POST or None, playgroup=playgroup)
    if request.method == 'POST' and form.is_valid():
        league = form.save(commit=False)
        league.playgroup = playgroup
        league.created_by = request.user
        league.save()
        messages.success(request, _('Box league created.'))
        return HttpResponseRedirect(box_league_url(league, 'pmc-pg-box-league-manage'))
    return render(request, 'pmc/pg-box-league-form.html', {'form': form})


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@is_pg_staff
def edit_playgroup_box_league(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    form = BoxLeagueForm(request.POST or None, instance=league,
                         playgroup=league.playgroup)
    tier_names_by_level = league.get_tier_names_by_level()
    named_level_count = max(tier_names_by_level, default=0)
    tier_formset = BoxLeagueTierNameFormSet(
        request.POST or None,
        prefix='tiers',
        initial=[{'name': tier_names_by_level.get(level, '')}
                 for level in range(1, named_level_count + 1)],
    )
    if request.method == 'POST' and form.is_valid() and tier_formset.is_valid():
        form.save()
        league.rename_tiers(tier_formset.get_tier_names())
        messages.success(request, _('Box league settings saved.'))
        return HttpResponseRedirect(box_league_url(league, 'pmc-pg-box-league-manage'))
    return render(request, 'pmc/pg-box-league-form.html', {
        'form': form,
        'tier_formset': tier_formset,
        'league': league,
        'active_tab': 'settings',
    })


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@is_pg_member
def playgroup_box_league_detail(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    session = league.get_current_session()
    if session:
        return HttpResponseRedirect(box_league_session_url(session))
    return render_box_league_session(request, league, None)


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@is_pg_member
def playgroup_box_league_session(request, slug, league_id, number):
    league = get_box_league_or_404(slug, league_id)
    return render_box_league_session(
        request, league, get_box_league_session_or_404(league, number))


def render_box_league_session(request, league, session):
    viewer_member = PlaygroupMember.objects.filter(
        playgroup=league.playgroup, user=request.user).first()
    box_summaries = session.get_box_summaries(viewer_member) if session else []
    assigned_member_ids = {
        standing.member.pk for summary in box_summaries for standing in summary.standings}
    confirmed_member_ids = session.get_confirmed_member_ids() if session and session.is_proposed() else set()
    waiting_members = [
        roster_entry.member
        for roster_entry in league.roster.select_related('member__user')
        if roster_entry.member_id not in assigned_member_ids
    ]
    is_session_open = session is not None and not session.is_completed()
    placed_player_count = len(assigned_member_ids)
    viewer_summary = next((summary for summary in box_summaries if summary.is_viewer_box), None)
    viewer_unplayed_matches = [
        box_match for box_match in (viewer_summary.box_matches if viewer_summary else [])
        if box_match.match.involves(viewer_member) and not box_match.match.has_result()
    ]
    is_on_roster = league.is_on_roster(viewer_member)
    viewer_has_confirmed = viewer_member is not None and viewer_member.pk in confirmed_member_ids
    awaiting_confirmation = session is not None and session.is_proposed() and is_on_roster and not viewer_has_confirmed
    awaiting_results = session is not None and session.is_active() and bool(viewer_unplayed_matches)
    return render(request, 'pmc/pg-box-league-session.html', {
        'next_step_is_due': awaiting_confirmation or awaiting_results,
        'viewer_next_match': viewer_unplayed_matches[0] if viewer_unplayed_matches else None,
        'viewer_games_left': len(viewer_unplayed_matches),
        'proposal': league.get_proposed_session(),
        'placed_player_count': placed_player_count,
        'suggested_box_count': league.suggested_box_count(placed_player_count),
        'resize_form': BoxProposalResizeForm(
            initial={'box_count': len(box_summaries)}) if session and session.is_proposed() else None,
        'add_box_form': BoxAddForm(session=session) if is_session_open else None,
        'league': league,
        'session': session,
        'box_summaries': box_summaries,
        'viewer_summary': viewer_summary,
        'previous_session': session.get_previous_session() if session else None,
        'next_session': session.get_next_session() if session else None,
        'is_on_roster': is_on_roster,
        'confirmed_member_ids': confirmed_member_ids,
        'viewer_has_confirmed': viewer_has_confirmed,
        'waiting_members': waiting_members,
        'is_stale_proposal': session is not None and session.is_stale_proposal(),
        'assignment_form': BoxAssignmentForm(session=session, box_summaries=box_summaries) if is_session_open else None,
    })


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@is_pg_staff
def manage_playgroup_box_league(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    current_session = league.get_active_session() or league.get_proposed_session()
    box_name_by_member_id = {}
    if current_session:
        for summary in current_session.get_box_summaries():
            for standing in summary.standings:
                box_name_by_member_id[standing.member.pk] = summary.name
    return render(request, 'pmc/pg-box-league-manage.html', {
        'league': league,
        'active_tab': 'sessions' if request.GET.get('tab') == 'sessions' else 'players',
        'sessions': league.sessions.order_by('-number'),
        'current_session': current_session,
        'proposal': league.get_proposed_session(),
        'roster': [
            (roster_entry, box_name_by_member_id.get(roster_entry.member_id))
            for roster_entry in league.roster.select_related('member__user')
        ],
        'add_member_form': BoxLeagueAddMemberForm(league=league),
    })


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_member
def join_box_league(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    viewer_member = get_viewer_member_or_403(request, league.playgroup)
    return run_competition_action(
        request,
        lambda: league.join(viewer_member),
        _('You are in! You will be placed in a box when the next session starts.'),
        box_league_url(league),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_member
def leave_box_league(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    viewer_member = get_viewer_member_or_403(request, league.playgroup)
    return run_competition_action(
        request,
        lambda: league.leave(viewer_member),
        _('You have left the league.'),
        box_league_url(league),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_member
def confirm_box_league_session(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    viewer_member = get_viewer_member_or_403(request, league.playgroup)
    return run_competition_action(
        request,
        lambda: league.confirm(viewer_member),
        _('Thanks! You are confirmed for the next session.'),
        box_league_url(league),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_member
def sit_out_box_league_session(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    viewer_member = get_viewer_member_or_403(request, league.playgroup)
    return run_competition_action(
        request,
        lambda: league.withdraw_confirmation(viewer_member),
        _('You will sit out the next session.'),
        box_league_url(league),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_staff
def plan_box_league_session(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    return run_competition_action(
        request,
        league.plan_next_session,
        _('Next session proposed. Players can now confirm they are in.'),
        box_league_url(league, 'pmc-pg-box-league-proposal'),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@is_pg_member
def box_league_proposal(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    proposal = league.get_proposed_session()
    if proposal is None:
        return HttpResponseRedirect(box_league_url(league))
    return HttpResponseRedirect(box_league_session_url(proposal))


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_staff
def rebalance_box_league_session(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    return run_competition_action(
        request,
        league.rebalance_proposal,
        _('Proposal rebalanced using confirmed players.'),
        box_league_url(league, 'pmc-pg-box-league-proposal'),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_staff
def resize_box_league_session(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    form = BoxProposalResizeForm(request.POST)
    if not form.is_valid():
        report_invalid_form(request, form)
        return redirect_to(request, box_league_url(league, 'pmc-pg-box-league-proposal'))
    return run_competition_action(
        request,
        lambda: league.resize_proposal(form.cleaned_data['box_count']),
        _('Boxes updated.'),
        box_league_url(league, 'pmc-pg-box-league-proposal'),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_staff
def add_box_league_box(request, slug, league_id, number):
    league = get_box_league_or_404(slug, league_id)
    session = get_box_league_session_or_404(league, number)
    form = BoxAddForm(request.POST, session=session)
    if not form.is_valid():
        report_invalid_form(request, form)
        return redirect_to(request, box_league_session_url(session))
    return run_competition_action(
        request,
        lambda: league.add_box(session, form.cleaned_data['level']),
        _('Box added. Place players into it to create their matches.'),
        box_league_session_url(session),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_staff
def remove_box_league_box(request, slug, league_id, number, box_id):
    league = get_box_league_or_404(slug, league_id)
    session = get_box_league_session_or_404(league, number)
    box = get_object_or_404(Box, pk=box_id, session=session)
    return run_competition_action(
        request,
        lambda: league.remove_box(box),
        _('Box removed.'),
        box_league_session_url(session),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_staff
def discard_box_league_session(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    return run_competition_action(
        request,
        league.discard_proposal,
        _('Proposal discarded.'),
        box_league_url(league, 'pmc-pg-box-league-manage'),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@is_pg_staff
def start_box_league_session(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    proposal = league.get_proposed_session()
    if proposal is None:
        messages.error(request, _('There is no proposed session.'))
        return HttpResponseRedirect(box_league_url(league))
    today = date.today()
    form = BoxSessionStartForm(
        request.POST or None,
        initial={'starts_on': today, 'ends_on': league.suggested_end_date(today)},
    )
    if request.method == 'POST' and form.is_valid():
        return run_competition_action(
            request,
            lambda: league.start_session(
                form.cleaned_data['starts_on'], form.cleaned_data['ends_on']),
            _('Session %(number)s has started. Good luck, everyone!') % {'number': proposal.number},
            box_league_session_url(proposal),
        )
    return render(request, 'pmc/pg-box-league-start.html', {
        'league': league,
        'proposal': proposal,
        'form': form,
    })


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_staff
def assign_box_league_player(request, slug, league_id, number):
    league = get_box_league_or_404(slug, league_id)
    session = get_box_league_session_or_404(league, number)
    form = BoxAssignmentForm(
        request.POST, session=session, box_summaries=session.get_box_summaries())
    if not form.is_valid():
        report_invalid_form(request, form)
        return redirect_to(request, box_league_session_url(session))
    member = form.cleaned_data['member']
    return run_competition_action(
        request,
        lambda: league.assign_to_box(member, form.get_box()),
        _('%(name)s placed.') % {'name': member},
        box_league_session_url(session),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_staff
def remove_box_league_session_player(request, slug, league_id, number, member_id):
    league = get_box_league_or_404(slug, league_id)
    session = get_box_league_session_or_404(league, number)
    member = get_object_or_404(
        PlaygroupMember, pk=member_id, playgroup=league.playgroup)
    return run_competition_action(
        request,
        lambda: league.remove_from_session(member, session),
        _('%(name)s removed from this session.') % {'name': member},
        box_league_session_url(session),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_staff
def add_box_league_member(request, slug, league_id):
    league = get_box_league_or_404(slug, league_id)
    form = BoxLeagueAddMemberForm(request.POST, league=league)
    if not form.is_valid():
        report_invalid_form(request, form)
        return redirect_to(request, box_league_url(league, 'pmc-pg-box-league-manage'))
    member = form.cleaned_data['member']
    return run_competition_action(
        request,
        lambda: league.join(member),
        _('%(name)s added to the league.') % {'name': member},
        box_league_url(league, 'pmc-pg-box-league-manage'),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_staff
def remove_box_league_member(request, slug, league_id, member_id):
    league = get_box_league_or_404(slug, league_id)
    member = get_object_or_404(
        PlaygroupMember, pk=member_id, playgroup=league.playgroup)
    return run_competition_action(
        request,
        lambda: league.leave(member),
        _('%(name)s removed from the league.') % {'name': member},
        box_league_url(league, 'pmc-pg-box-league-manage'),
    )


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@is_pg_member
def record_box_match_result(request, slug, league_id, box_match_id):
    league = get_box_league_or_404(slug, league_id)
    box_match = get_box_match_or_404(league, box_match_id)
    match = box_match.match
    is_participant = request.user.pk in (match.player_one.user_id, match.player_two.user_id)
    is_organizer = league.is_organizer(request.user)
    if not is_participant and not is_organizer:
        raise PermissionDenied
    session_url = box_league_session_url(box_match.box.session)
    if not box_match.box.session.is_active():
        messages.error(request, _('Results can only be recorded while the session is active.'))
        return HttpResponseRedirect(session_url)
    if match.has_result() and not is_organizer:
        messages.error(request, _('This match already has a result. Ask an organizer to change it.'))
        return HttpResponseRedirect(session_url)

    form = MatchOutcomeForm(
        request.POST or None,
        match=match,
        initial=MatchOutcomeForm.initial_for(match.result) if match.has_result() else None,
    )
    if request.method == 'POST' and form.is_valid():
        save_result = league.change_result if match.has_result() else league.record_result
        return run_competition_action(
            request,
            lambda: save_result(box_match, form.get_winner(), request.user),
            _('Result recorded.'),
            session_url,
        )
    return render(request, 'pmc/pg-box-match-result.html', {
        'league': league,
        'box_match': box_match,
        'form': form,
        'session_url': session_url,
    })


@login_required
@requires_pg_feature(Feature.Keys.BOX_LEAGUES)
@require_POST
@is_pg_staff
def clear_box_match_result(request, slug, league_id, box_match_id):
    league = get_box_league_or_404(slug, league_id)
    box_match = get_box_match_or_404(league, box_match_id)
    return run_competition_action(
        request,
        lambda: league.clear_result(box_match, request.user),
        _('Result cleared.'),
        box_league_session_url(box_match.box.session),
    )


@login_required
def my_results(request):
    return render(request, 'pmc/g-my-results.html', {
        'results': exclude_upcoming_event_results(
            EventResult.objects.filter(
                user=request.user).order_by('-event__start_date')
        )
    })


@login_required
def my_keychain(request):
    profile = request.user.pmc_profile
    current_level = profile.get_level()
    next_level = profile.get_next_level()
    level_up_info = profile._get_level_up_info()
    my_results = profile.get_events(exclude_upcoming=True)

    return render(request, 'pmc/g-my-keychain.html', {
        'my_results': my_results,
        'events_won': my_results.filter(finishing_position=1),
        'num_game_wins': my_results.aggregate(Sum('num_wins'))['num_wins__sum'],
        'current_level': current_level,
        'next_level': next_level,
        'percent_level_up': level_up_info['percent_level_up'],
        'level_increment': level_up_info['level_increment'],
        'level_increment_progress': level_up_info['level_increment_progress'],
        'memberships': PlaygroupMember.objects.filter(
            user=request.user
        ),
        'global_playgroups': Playgroup.objects.filter(is_global=True),
        'pinned_awards': PinnedAward.get_pinned_awards_for_display(request.user),
    })


@login_required
def user_profile(request, username):
    user = get_object_or_404(get_user_model(), username__iexact=username)
    profile = user.pmc_profile
    current_level = profile.get_level()
    next_level = profile.get_next_level()
    level_up_info = profile._get_level_up_info()
    playgroup_memberships = PlaygroupMember.objects.filter(user=user)

    context = {
        'user': user,
        'profile': profile,
        'badges': Badge.with_user_badges(user).filter(user_badge_id__isnull=False),
        'achievements': Achievement.with_highest_user_achievements_tier(user).filter(user_achievement_tier__isnull=False),
        'trophies': Trophy.with_user_trophies(user).filter(user_trophy_amount__isnull=False),
        'current_level': current_level,
        'next_level': next_level,
        'percent_level_up': level_up_info['percent_level_up'],
        'level_increment': level_up_info['level_increment'],
        'level_increment_progress': level_up_info['level_increment_progress'],
        'playgroup_memberships': playgroup_memberships,
        'pinned_awards': PinnedAward.get_pinned_awards_for_display(user),
    }

    return render(request, 'pmc/g-user-profile.html', context)


@login_required
@is_pg_member
def manage_my_playgroup_profile(request, slug):
    member = get_object_or_404(
        PlaygroupMember,
        playgroup__slug=slug,
        user__username=request.user.username
    )
    if request.method == 'POST':
        form = PlaygroupMemberForm(request.POST, instance=member)
        if form.is_valid():
            form.save()
            messages.success(request, _('Profile updated.'))
            return HttpResponseRedirect(reverse('pmc-my-keychain'))

    else:
        form = PlaygroupMemberForm(instance=member)

    return render(request, 'pmc/pg-me-manage.html', {
        'form': form,
        'slug': slug,
    })


class PlaygroupMembersList(LoginRequiredMixin, generic.ListView):
    context_object_name = 'members'
    template_name = 'pmc/pg-members.html'

    def get_queryset(self):
        return PlaygroupMember.objects.filter(playgroup__slug=self.kwargs['slug'], is_hidden=False)

    @method_decorator(login_required)
    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        playgroup = Playgroup.objects.filter(slug=self.kwargs['slug']).first()
        if playgroup and playgroup.is_global:
            return HttpResponseRedirect(reverse('pmc-pg-detail', kwargs={'slug': self.kwargs['slug']}))
        return super().dispatch(request, *args, **kwargs)


@login_required
def playgroup_member_detail(request, slug, username):
    is_pg_member = PlaygroupMember.objects.filter(
        playgroup__slug=slug,
        user=request.user
    ).count() > 0
    if not is_pg_member:
        return redirect_to(request, reverse('pmc-user-profile', kwargs={'username': username}))
    return user_profile(request, username)


@login_required
@is_pg_staff
def playgroup_member_manage(request, slug, username):
    member = get_object_or_404(
        PlaygroupMember,
        user__username__iexact=username,
        playgroup__slug=slug
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'assign_badge':
            pk = request.POST.get('badge_id')
            badge = get_object_or_404(Badge, pk=pk)
            if not badge.is_eo_assignable:
                messages.error(request, _(
                    'This badge only  be assigned by KeyChain staff.'))
                return redirect_to(request, reverse('pmc-pg-member-manage', kwargs={
                    'slug': slug,
                    'username': username
                }))
            UserBadge.objects.get_or_create(
                user=member.user,
                badge=badge
            )
            messages.success(request, _('Badge assigned.'))
            return redirect_to(request, reverse('pmc-pg-member-manage', kwargs={
                'slug': slug,
                'username': username
            }))

    if request.method == 'DELETE':
        member.delete()
        messages.success(request, _('Member removed.'))
        return redirect_to(request, reverse('pmc-pg-members', kwargs={'slug': slug}))

    badges = Badge.with_user_badges(member.user).all()
    context = {'member': member, 'badges': badges}
    return render(request, 'pmc/pg-member-manage.html', context)


class PlaygroupEventsList(LoginRequiredMixin, generic.ListView):
    context_object_name = 'events'
    template_name = 'pmc/pg-events.html'
    paginate_by = 25

    def get_queryset(self):
        return Event.objects.filter(playgroups__slug=self.kwargs['slug'])

    @method_decorator(login_required)
    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


@login_required
def event_detail_generic(request, pk):
    pg_events = PlaygroupEvent.objects.filter(
        event__pk=pk,
        playgroup__members__user=request.user
    )
    try:
        return HttpResponseRedirect(reverse('pmc-pg-event-detail', kwargs={
            'slug': pg_events.first().playgroup.slug,
            'pk': pk
        }))
    except:
        playgroups = Playgroup.objects.filter(events__pk=pk)
        return render(request, 'pmc/g-event-not-found.html', {'playgroups': playgroups})


class EventDetail(generic.DetailView):
    model = Event
    template_name = 'pmc/pg-event-detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        player_count = self.object.results.count()
        context['player_count'] = player_count
        if user.is_authenticated:
            context['is_registered'] = EventResult.objects.filter(
                event=self.object, user=user).exists()
            context['is_member'] = PlaygroupMember.objects.filter(
                user=user, playgroup__slug=self.kwargs['slug']).exists()
            context['my_result'] = EventResult.objects.filter(
                event=self.object, user=user).first()
            has_own_result = context['my_result'] is not None
            context['other_player_count'] = player_count - \
                (1 if has_own_result else 0)
        else:
            context['is_registered'] = False
            context['is_member'] = False
            context['my_result'] = None
            context['other_player_count'] = player_count
        linked_tournament = self.object.tournaments.first()
        context['linked_tournament'] = linked_tournament
        if linked_tournament:
            context['linked_tournament_url'] = main_site_url(
                self.request, f'/tourney/{linked_tournament.code}/')
        return context


@login_required
@is_pg_member
def result_detail(request, slug, pk):
    event_result = get_object_or_404(EventResult, pk=pk)
    # todo - ensure that the event is associated with the playgroup
    is_allowed_to_edit = request.user == event_result.user or PlaygroupMember.objects.filter(
        user=request.user, playgroup__slug=slug, is_staff=True).exists()

    if event_result.uploaded_deck_link and event_result.uploaded_deck_lookup_attempts < event_result.max_deck_lookup_attempts:
        try:
            event_result.add_deck_by_uploaded_link()
        except Exception:
            pass

    if request.method == 'POST':
        if not is_allowed_to_edit:
            messages.error(request, _(
                'You are not allowed to edit this result.'))
            return HttpResponse('', content_type='text/plain')

        if request.POST.get('action') == 'add':
            if event_result.event_result_decks.count() >= 6:
                messages.error(request, _(
                    'Hold up! You\'re maxed out on decks for this result.'))
                return HttpResponse('', content_type='text/plain')

            try:
                form = EventResultDeckForm(request.POST)
                if form.is_valid():
                    deck = form.save()
                    try:
                        EventResultDeck.objects.create(
                            event_result=event_result,
                            deck=deck
                        )

                        event_result.uploaded_deck_link = None
                        event_result.uploaded_deck_lookup_attempts = 0
                        event_result.save()
                    except IntegrityError:
                        messages.error(request, _(
                            'Hold up, you may have already added that deck!'))
                        return HttpResponse('', content_type='text/plain')
            except:
                messages.error(request, _(
                    'Oops! Something went wrong. Please check your deck link and try again.'))
                return HttpResponse('', content_type='text/plain')

            if request.htmx:
                context = {
                    'deck': deck,
                    'is_allowed_to_edit': is_allowed_to_edit,
                }
                return render(request, 'pmc/pg-result-detail.html#deck-list-item', context)

        elif request.POST.get('action') == 'remove':
            deck_id = request.POST.get('deck_id')
            event_result.event_result_decks.filter(deck__id=deck_id).delete()
            return HttpResponse('Done.', content_type='text/plain')

    else:
        form = EventResultDeckForm()

    context = {
        'event_result': event_result,
        'form': form,
        'is_allowed_to_edit': is_allowed_to_edit,
    }
    return render(request, 'pmc/pg-result-detail.html', context)


@login_required
@is_pg_staff
def manage_event(request, slug, pk):
    event = get_object_or_404(Event, pk=pk)
    if request.method == 'POST':
        form = EventUpdateForm(request.POST, instance=event, user=request.user)
        if form.is_valid():
            event = form.save()
            RankingPointsService.assign_points_for_event(event)
            messages.success(request, _('Event updated.'))
            return HttpResponseRedirect(reverse('pmc-pg-event-manage', kwargs={
                'slug': slug,
                'pk': event.id,
            }))
        else:
            messages.error(request, _(
                'Oops! That\'s not quite right. Check the form and try again.'))
    else:
        form = EventUpdateForm(instance=event, user=request.user)
    linked_tournament = event.tournaments.first()
    context = {
        'object': event,
        'form': form,
        'linked_tournament': linked_tournament,
        'linked_tournament_url': main_site_url(request, f'/tourney/{linked_tournament.code}/') if linked_tournament else None,
        'create_tournament_url': main_site_url(request, f'/tourney/create/from-event/{event.pk}/'),
        'can_start_tourney': event.is_eligible_for_tourney_creation,
    }
    return render(request, 'pmc/pg-event-manage.html', context)


@require_POST
@login_required
@is_pg_staff
def delete_event(request, slug, pk):
    event = get_object_or_404(Event, pk=pk)
    # TODO - ensure that the event is associated with the playgroup
    event.delete()
    messages.success(request, _('Event deleted.'))
    return redirect_to(request, reverse('pmc-pg-events', kwargs={'slug': slug}))


@login_required
@is_pg_member
def playgroup_leaderboard(request, slug, pk=None):
    playgroup = get_object_or_404(Playgroup, slug=slug)

    leaderboards = Leaderboard.objects.exclude(
        leaderboard_settings__playgroup=playgroup,
        leaderboard_settings__is_leaderboard_hidden=True
    )

    if pk is None:
        return HttpResponseRedirect(reverse('pmc-pg-leaderboard', kwargs={
            'slug': slug,
            'pk': leaderboards.first().pk
        }))

    leaderboard = get_object_or_404(Leaderboard, pk=pk)

    if 'season' in request.GET and 'period' in request.GET:
        try:
            season_id = int(request.GET.get('season'))
            period_id = int(request.GET.get('period'))
            period = LeaderboardSeasonPeriod.objects.filter(
                id=period_id).first()
            if period and period.season_id != season_id:
                params = request.GET.copy()
                params.pop('period')
                return HttpResponseRedirect(f"{request.path}?{params.urlencode()}")
        except (ValueError, TypeError):
            pass

    rank_filters = {
        'leaderboard': pk,
        'playgroup__slug': slug
    }

    form_data = request.GET if request.GET else None
    season_period_form = LeaderboardSeasonPeriodForm(leaderboard, form_data)

    try:
        rank_filters['period__season'] = season_period_form.data.get(
            'season') or season_period_form.fields['season'].initial
        rank_filters['period'] = season_period_form.data.get(
            'period') or season_period_form.fields['period'].initial
    except KeyError:
        pass

    rankings = PlayerRank.objects.filter(**rank_filters)
    paginator = Paginator(rankings, 25)
    page_number = request.GET.get('page', 1)
    try:
        rankings_page = paginator.page(page_number)
    except PageNotAnInteger:
        rankings_page = paginator.page(1)
    except EmptyPage:
        rankings_page = paginator.page(paginator.num_pages)

    return render(request, 'pmc/pg-leaderboard.html', {
        'leaderboards': leaderboards,
        'season_period_form': season_period_form,
        'rankings_page': rankings_page,
        'total_count': rankings.count(),
        'pk': pk,
    })


@login_required
def global_leaderboard(request, pk=None):
    if pk is None:
        return HttpResponseRedirect(reverse('pmc-leaderboard', kwargs={
            'pk': Leaderboard.objects.first().pk
        }))

    leaderboard = get_object_or_404(Leaderboard, pk=pk)

    if 'season' in request.GET and 'period' in request.GET:
        try:
            season_id = int(request.GET.get('season'))
            period_id = int(request.GET.get('period'))
            period = LeaderboardSeasonPeriod.objects.filter(
                id=period_id).first()
            if period and period.season_id != season_id:
                params = request.GET.copy()
                params.pop('period')
                return HttpResponseRedirect(f"{request.path}?{params.urlencode()}")
        except (ValueError, TypeError):
            pass

    rank_filters = {
        'leaderboard': pk,
        'playgroup': None
    }
    season_period_form = LeaderboardSeasonPeriodForm(
        leaderboard, request.GET or None)
    try:
        rank_filters['period__season'] = season_period_form.data.get(
            'season') or season_period_form.fields['season'].initial
        rank_filters['period'] = season_period_form.data.get(
            'period') or season_period_form.fields['period'].initial
    except KeyError:
        pass

    rankings = PlayerRank.objects.filter(**rank_filters)
    paginator = Paginator(rankings, 25)
    page_number = request.GET.get('page', 1)
    try:
        rankings_page = paginator.page(page_number)
    except PageNotAnInteger:
        rankings_page = paginator.page(1)
    except EmptyPage:
        rankings_page = paginator.page(paginator.num_pages)

    return render(request, 'pmc/g-leaderboard.html', {
        'leaderboards': Leaderboard.objects.all(),
        'season_period_form': season_period_form,
        'rankings_page': rankings_page,
        'total_count': rankings.count(),
        'pk': pk,
    })


@login_required
@is_pg_staff
@transaction.atomic
def submit_event_results(request, slug):
    form_errors = []
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            event = form.save()
            PlaygroupEvent.objects.create(
                playgroup=Playgroup.objects.get(slug=slug),
                event=event
            )
            event_results = []
            csv_file = form.cleaned_data['results_file']
            if csv_file:
                decoded_file = csv_file.read().decode('utf-8')
                reader = csv.DictReader(decoded_file.splitlines())
                available_headers = [
                    'user', 'username', 'finishing_position', 'place', 'num_wins', 'wins', 'num_losses', 'losses', 'num_ties', 'ties', 'deck', 'list_link']
                if not set(reader.fieldnames).issubset(set(available_headers)):
                    form_errors.append(
                        'Your results file may include only these columns: {columns}'.format(
                            columns=', '.join(available_headers))
                    )
                elif not 'user' in reader.fieldnames and not 'username' in reader.fieldnames:
                    form_errors.append(
                        'Your results file must include a "user" column')
                else:
                    User = get_user_model()
                    playstile_aliases = [
                        ('username', 'user'),
                        ('place', 'finishing_position'),
                        ('wins', 'num_wins'),
                        ('losses', 'num_losses'),
                        ('ties', 'num_ties'),
                        ('list_link', 'deck'),
                    ]

                    for row in reader:
                        for old_key, new_key in playstile_aliases:
                            if old_key in row:
                                row[new_key] = row.pop(old_key)
                        username = row.pop('user')

                        row['uploaded_deck_link'] = row.pop('deck', None)

                        row = {key: (None if value == '' else value)
                               for key, value in row.items()}
                        try:
                            user = User.objects.get(username__iexact=username)
                            event_results.append(EventResult(
                                user=user,
                                event=event,
                                **row
                            ))
                        except User.DoesNotExist:
                            form_errors.append(f'No such user: {username}')

            if not form_errors:
                if event_results:
                    results = EventResult.objects.bulk_create(event_results)
                    RankingPointsService.assign_points_for_results(
                        results,
                        event.player_count or len(results)
                    )

                messages.success(request, _('Event created.'))
                return HttpResponseRedirect(reverse('pmc-pg-event-detail', kwargs={
                    'slug': slug,
                    'pk': event.id,
                }))

        else:
            print(form.errors)
    else:
        form = EventForm(
            user=request.user,
            playgroup=Playgroup.objects.get(slug=slug)
        )
    return render(request, 'pmc/pg-submit-event-results.html', {
        'form_errors': form_errors,
        'form': form,
    })


def typography(request):
    return render(request, 'pmc/typography.html')


def about(request):
    return render(request, 'pmc/about.html')


def about_ranking_points(request):
    current_version = RankingPointsMapVersion.objects.filter(
        effective_on__lte=date.today()
    ).order_by('-effective_on').first()

    form = RankingPointsMapVersionForm(request.GET or None)
    selected_version = current_version

    if form.is_valid():
        selected_version = form.cleaned_data['version']
    else:
        form = RankingPointsMapVersionForm(
            initial={'version': current_version})

    return render(request, 'pmc/g-about-ranking-points.html', {
        'form': form,
        'selected_version': selected_version,
        'ranges_by_size': [
            ('3 Players', RankingPointsMap.list_points_for_fp_ranges(
                3, selected_version)),
            ('4 Players', RankingPointsMap.list_points_for_fp_ranges(
                4, selected_version)),
            ('5 to 8 Players', RankingPointsMap.list_points_for_fp_ranges(
                8, selected_version)),
            ('9 to 16 Players', RankingPointsMap.list_points_for_fp_ranges(
                16, selected_version)),
            ('17 to 32 Players', RankingPointsMap.list_points_for_fp_ranges(
                32, selected_version)),
            ('33 to 64 Players', RankingPointsMap.list_points_for_fp_ranges(
                64, selected_version)),
        ]
    })


def attributions(request):
    return render(request, 'pmc/g-attributions.html')


@login_required
def change_avatar(request):
    if request.method == 'POST':
        avatar_id = request.POST.get('avatar')
        avatar = Avatar.objects.get(pk=avatar_id)
        request.user.pmc_profile.avatar = avatar
        request.user.pmc_profile.save()
        return HttpResponseRedirect(reverse('pmc-manage-avatar'))

    current_level = request.user.pmc_profile.get_level()
    return render(request, 'pmc/g-change-avatar.html', {
        'current_avatar': request.user.pmc_profile.get_avatar(),
        'categories': AvatarCategory.objects.filter(is_hidden=False),
        'current_level': current_level.level,
    })


@login_required
def change_background(request):
    if request.method == 'POST':
        background_id = request.POST.get('background')
        background = Background.objects.get(pk=background_id)
        request.user.pmc_profile.background = background
        request.user.pmc_profile.save()
        return HttpResponseRedirect(reverse('pmc-manage-background'))

    current_level = request.user.pmc_profile.get_level()
    return render(request, 'pmc/g-change-background.html', {
        'current_background': request.user.pmc_profile.get_background(),
        'categories': BackgroundCategory.objects.filter(is_hidden=False),
        'current_level': current_level.level,
    })


@require_POST
@login_required
@is_pg_staff
def assign_event_points(request, slug, pk):
    event = get_object_or_404(Event, pk=pk)
    # TODO verify that the event is associated with the playgroup
    RankingPointsService.assign_points_for_event(event)
    messages.success(request, _('Ranking points updated.'))
    return HttpResponseRedirect(reverse('pmc-pg-event-detail', kwargs={'slug': slug, 'pk': pk}))


@login_required
@is_pg_staff
def manage_event_result(request, slug, pk):
    if request.method == 'DELETE':
        result = get_object_or_404(EventResult, pk=pk)
        result.delete()
        RankingPointsService.assign_points_for_event(result.event)
        messages.success(request, _('Result removed.'))
        if request.htmx:
            context = {
                'playgroup': Playgroup.objects.get(slug=slug),
                'object': result.event,
            }
            return render(request, 'pmc/pg-event-manage.html#results-table', context)
        return HttpResponseRedirect(reverse('pmc-pg-event-manage', kwargs={'slug': slug, 'pk': result.event.pk}))
    elif request.method == 'POST':
        result = get_object_or_404(EventResult, pk=pk)
        result.finishing_position = request.POST.get(
            'finishing_position') or None
        result.num_wins = request.POST.get('num_wins') or None
        result.num_losses = request.POST.get('num_losses') or None
        result.num_ties = request.POST.get('num_ties') or None
        result.save()
        RankingPointsService.assign_points_for_event(result.event)
        messages.success(request, _('Result updated.'))
        if request.htmx:
            context = {
                'playgroup': Playgroup.objects.get(slug=slug),
                'object': result.event,
            }
            return render(request, 'pmc/pg-event-manage.html#results-table', context)
        return HttpResponseRedirect(reverse('pmc-pg-event-manage', kwargs={'slug': slug, 'pk': result.event.pk}))


@login_required
@is_pg_staff
def add_event_result(request, slug, pk):
    if request.method == 'POST':
        status = HTTPStatus.OK
        event = get_object_or_404(Event, pk=pk)
        # TODO verify that the event is associated with the playgroup
        post_data = request.POST.dict()
        result_data = {key: (None if value == '' else value)
                       for key, value in post_data.items()}
        username = result_data.pop('username')
        User = get_user_model()
        try:
            result = EventResult(
                user=User.objects.get(username__iexact=username),
                event=event,
                **result_data
            )
            result.event = event
            result.save()
            RankingPointsService.assign_points_for_event(event)
            messages.success(request, _('Result added.'))
        except User.DoesNotExist:
            messages.error(request, _(
                'Oops! We could not find a user named {}.'.format(username)))
            status = HTTPStatus.BAD_REQUEST
        except IntegrityError as e:
            messages.error(request, _(
                'Oops! We could not save that result, you may have one for that user already.'))
            status = HTTPStatus.BAD_REQUEST
        except Exception:
            messages.error(request, _('Oops! Something went wrong.'))
            status = HTTPStatus.INTERNAL_SERVER_ERROR
        if request.htmx:
            context = {
                'playgroup': Playgroup.objects.get(slug=slug),
                'object': event,
            }
            return render(
                request,
                'pmc/pg-event-manage.html#results-table',
                context,
                status=status
            )
        return HttpResponseRedirect(reverse('pmc-pg-event-manage', kwargs={'slug': slug, 'pk': pk}))


@require_POST
@login_required
def toggle_event_registration(request, slug, pk):
    event = get_object_or_404(Event, pk=pk)
    if not event.is_registration_open:
        messages.error(request, _('Registration is not open for this event.'))
    else:
        existing = EventResult.objects.filter(
            event=event, user=request.user).first()
        if existing:
            existing.delete()
            messages.success(request, _('Registration cancelled.'))
        else:
            EventResult.objects.create(event=event, user=request.user)
            messages.success(request, _('You are registered!'))
    return HttpResponseRedirect(reverse('pmc-pg-event-detail', kwargs={'slug': slug, 'pk': pk}))


@csrf_exempt
@require_POST
@api_key_required
@transaction.atomic
def refresh_leaderboard(request, pk):
    leaderboard = Leaderboard.objects.get(pk=pk)
    period = leaderboard.get_period_for_date(date.today())
    if leaderboard.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.MONTH:
        order_by = 'total_points'
    elif leaderboard.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.SEASON:
        order_by = 'total_points'
    elif leaderboard.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.ALL_TIME:
        order_by = 'total_points'
    else:
        raise ValueError('Invalid leaderboard period frequency')

    if not period.is_locked:
        RankingPointsService.assign_points_for_leaderboard(
            leaderboard,
            period,
            order_by=order_by
        )

    last_week_period = leaderboard.get_period_for_date(
        date.today() - timedelta(days=7))
    if last_week_period.pk != period.pk and not last_week_period.is_locked:
        RankingPointsService.assign_points_for_leaderboard(
            leaderboard,
            last_week_period,
            order_by=order_by
        )

    LeaderboardSeasonPeriod.objects.update_all_lock_statuses()

    LeaderboardLog.objects.create(
        leaderboard=leaderboard
    ).save()
    return HttpResponse('Done.', content_type='text/plain')


@login_required
def manage_my_pmc_profile(request):
    profile = request.user.pmc_profile
    if request.method == 'POST':
        form = PmcProfileForm(request.POST, instance=profile)
        username_form = EditUsernameForm(
            request.POST, instance=request.user)
        privacy_form = PmcProfilePrivacyForm(
            request.POST, instance=profile)
        if form.is_valid() and username_form.is_valid() and privacy_form.is_valid():
            form.save()
            username_form.save()
            username_form.request_email_change_if_changed(request)
            privacy_form.save()
            messages.success(request, _('Profile updated.'))
            return HttpResponseRedirect(reverse('pmc-my-keychain-manage'))
        else:
            messages.error(request, _(
                'Oops! That\'s not quite right. Check the form and try again.'))

    else:
        form = PmcProfileForm(instance=profile)
        username_form = EditUsernameForm(
            instance=request.user)
        privacy_form = PmcProfilePrivacyForm(
            instance=profile)

    return render(request, 'pmc/g-me-manage.html', {
        'form': form,
        'username_form': username_form,
        'privacy_form': privacy_form,
    })


@require_POST
@login_required
def set_master_vault_data(request):
    profile = request.user.pmc_profile

    if request.POST.get('disconnect'):
        profile.mv_id = None
        profile.mv_username = None
        profile.mv_qrcode_message = None
        profile.save()
        messages.success(request, _('Master Vault account disconnected.'))
        return HttpResponseRedirect(reverse('pmc-my-keychain-manage'))

    message = request.POST.get('qr_code_message')
    try:
        message_data = json.loads(message)
        profile.mv_id = message_data['id']
        profile.mv_username = message_data['un']
        profile.mv_qrcode_message = message
        profile.save_qrcode()
        profile.save()
        messages.success(request, _('Master Vault account connected.'))
    except Exception as e:
        messages.error(request, _('Oops! Something went wrong.'))
    return HttpResponseRedirect(reverse('pmc-my-keychain-manage'))


@require_POST
@login_required
@is_pg_staff
def add_pg_member_by_qrcode(request, slug):
    message = request.POST.get('qr_code_message')
    try:
        message_data = json.loads(message)
        mv_id = message_data['id']
        User = get_user_model()
        member, _created = PlaygroupMember.objects.get_or_create(
            playgroup=Playgroup.objects.get(slug=slug),
            user=User.objects.get(pmc_profile__mv_id=mv_id)
        )
        href_member_detail = reverse('pmc-pg-member-detail', kwargs={
            'slug': slug,
            'username': member.user.username
        })
        msg = _(
            '{} added. View <a href="{}">their profile</a>.').format(member, href_member_detail)
        messages.success(request, mark_safe(msg))
        return HttpResponseRedirect(reverse('pmc-pg-members', kwargs={
            'slug': slug
        }))
    except Exception as e:
        print(e)
        messages.error(request, _('Oops! Something went wrong.'))
    return HttpResponseRedirect(reverse('pmc-pg-members', kwargs={'slug': slug}))


@require_POST
@login_required
@is_pg_staff
def checkin_player_by_qrcode(request, slug, pk):
    event = get_object_or_404(Event, pk=pk)
    message = request.POST.get('qr_code_message')
    redirect_url = reverse('pmc-pg-event-detail', kwargs={'slug': slug, 'pk': pk})
    try:
        message_data = json.loads(message)
        mv_id = message_data['id']
    except (json.JSONDecodeError, KeyError, TypeError):
        messages.error(request, _('Unrecognized QR code.'))
        return HttpResponseRedirect(redirect_url)
    User = get_user_model()
    try:
        user = User.objects.get(pmc_profile__mv_id=mv_id)
    except User.DoesNotExist:
        messages.error(request, _('No KeyChain account found for this QR code.'))
        return HttpResponseRedirect(redirect_url)
    if EventResult.objects.filter(event=event, user=user).exists():
        messages.info(request, _('{} is already checked in.').format(user))
        return HttpResponseRedirect(redirect_url)
    EventResult.objects.create(event=event, user=user)
    messages.success(request, _('{} has been checked in.').format(user))
    return HttpResponseRedirect(redirect_url)


@require_POST
@login_required
@is_pg_staff
def add_pg_member_by_username(request, slug):
    username = request.POST.get('username').strip()
    try:
        User = get_user_model()
        member, created = PlaygroupMember.objects.get_or_create(
            playgroup=Playgroup.objects.get(slug=slug),
            user=User.objects.get(username__iexact=username)
        )
        href_member_detail = reverse('pmc-pg-member-detail', kwargs={
            'slug': slug,
            'username': member.user.username
        })

        if created:
            msg = _(
                '{} added. View <a href="{}">their profile</a>.').format(member, href_member_detail)
            messages.success(request, mark_safe(msg))
            context = {
                'member': member,
                'playgroup': Playgroup.objects.get(slug=slug),
            }
            return render(request, 'pmc/pg-members.html#member-list-item', context)
        else:
            msg = _(
                '{} is already a member. View <a href="{}">their profile</a>.').format(member, href_member_detail)
            messages.success(request, mark_safe(msg))
    except User.DoesNotExist:
        messages.error(request, _(
            'Oops! We could not find a user with that username.'))
    except Exception as e:
        print(e)
        messages.error(request, _('Oops! Something went wrong.'))
    return HttpResponse('')


@login_required
@is_pg_staff
def get_result_submission_template(request, slug):
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="results.csv"'}
    )
    writer = csv.writer(response)
    writer.writerow(['user', 'finishing_position',
                    'num_wins', 'num_losses', 'num_ties', 'deck'])
    members = PlaygroupMember.objects.filter(playgroup__slug=slug)
    for member in members:
        writer.writerow([member.user.username, '', '', '', ''])
    return response


@login_required
def my_awards(request):
    pinned = PinnedAward.objects.filter(user=request.user)
    pinned_map = {(p.award_type, p.award_id): p.pk for p in pinned}
    context = {
        'badges': Badge.with_user_badges(request.user).all(),
        'achievements': Achievement.with_highest_user_achievements_tier(request.user).all(),
        'trophies': Trophy.with_user_trophies(request.user).all(),
        'pinned_awards': PinnedAward.get_pinned_awards_for_display(request.user),
        'pinned_map': pinned_map,
        'pin_count': pinned.count(),
    }
    return render(request, 'pmc/g-my-awards.html', context)


@login_required
def my_badge_detail(request, pk):
    badge = get_object_or_404(Badge, pk=pk)
    try:
        my_badge = UserBadge.objects.get(badge=badge, user=request.user)
    except UserBadge.DoesNotExist:
        my_badge = None
    context = {'badge': badge, 'my_badge': my_badge}
    return render(request, 'pmc/g-my-badge-detail.html', context)


@login_required
def my_achievement_detail(request, pk):
    achievement = get_object_or_404(Achievement, pk=pk)
    context = {
        'achievement': Achievement.with_highest_user_achievements_tier(request.user).filter(pk=pk).first(),
        'tiers': AchievementTier.objects.filter(achievement=achievement).annotate(
            earned_count=Count('user_achievement_tiers', distinct=True)
        ),
        'my_stat': AwardAssignmentService.get_user_criteria_value(
            request.user, achievement),
    }
    return render(request, 'pmc/g-my-achievement-detail.html', context)


@login_required
def my_trophy_detail(request, pk):
    trophy = get_object_or_404(Trophy, pk=pk)
    try:
        my_trophy = UserTrophy.objects.get(trophy=trophy, user=request.user)
    except UserTrophy.DoesNotExist:
        my_trophy = None
    top_user_trophies = UserTrophy.objects.filter(
        trophy=trophy).order_by('-amount')[:5]
    context = {
        'trophy': trophy,
        'my_trophy': my_trophy,
        'top_user_trophies': top_user_trophies
    }
    return render(request, 'pmc/g-my-trophy-detail.html', context)


def _render_awards_content(request):
    pinned = PinnedAward.objects.filter(user=request.user)
    pinned_map = {(p.award_type, p.award_id): p.pk for p in pinned}
    return render(request, 'pmc/_awards-content.html', {
        'badges': Badge.with_user_badges(request.user).all(),
        'achievements': Achievement.with_highest_user_achievements_tier(request.user).all(),
        'trophies': Trophy.with_user_trophies(request.user).all(),
        'pinned_awards': PinnedAward.get_pinned_awards_for_display(request.user),
        'pinned_map': pinned_map,
        'pin_count': pinned.count(),
    })


@login_required
@require_POST
def pin_award(request):
    award_type = int(request.POST.get('award_type', -1))
    award_id = int(request.POST.get('award_id', 0))

    if award_type not in PinnedAward.AwardTypeOptions.values:
        return HttpResponse(status=HTTPStatus.BAD_REQUEST)

    position = PinnedAward.next_position(request.user)
    if position is None:
        return HttpResponse(status=HTTPStatus.BAD_REQUEST)

    already_pinned = PinnedAward.objects.filter(
        user=request.user, award_type=award_type, award_id=award_id
    ).exists()
    if already_pinned:
        return _render_awards_content(request)

    PinnedAward.objects.create(
        user=request.user,
        award_type=award_type,
        award_id=award_id,
        position=position,
    )
    return _render_awards_content(request)


@login_required
@require_POST
def unpin_award(request, pk):
    PinnedAward.objects.filter(pk=pk, user=request.user).delete()
    PinnedAward.recompact_positions(request.user)
    return _render_awards_content(request)


@login_required
@require_POST
def reorder_pinned_awards(request):
    pin_order = request.POST.get('pin_order', '')
    if not pin_order:
        return HttpResponse(status=HTTPStatus.BAD_REQUEST)

    pin_ids = [int(x) for x in pin_order.split(',') if x.strip()]
    pins = PinnedAward.objects.filter(user=request.user, pk__in=pin_ids)
    pin_map = {p.pk: p for p in pins}

    with transaction.atomic():
        for i, pin_id in enumerate(pin_ids):
            PinnedAward.objects.filter(
                pk=pin_id, user=request.user
            ).update(position=6 + i)

        for i, pin_id in enumerate(pin_ids, start=1):
            PinnedAward.objects.filter(
                pk=pin_id, user=request.user
            ).update(position=i)

    return _render_awards_content(request)


@api_key_required
def list_refreshable_trophies(request):
    pmc_ids = list(Trophy.objects.exclude(
        criteria=AwardBase.CriteriaTypeOptions.manually_awarded
    ).values_list('pmc_id', flat=True).order_by('pmc_id'))
    return JsonResponse({'pmc_ids': pmc_ids})


@api_key_required
def list_refreshable_achievements(request):
    pmc_ids = list(Achievement.objects.values_list(
        'pmc_id', flat=True).order_by('pmc_id'))
    return JsonResponse({'pmc_ids': pmc_ids})


@csrf_exempt
@require_POST
@api_key_required
@transaction.atomic
def refresh_trophy(request, pmc_id):
    AwardAssignmentService.refresh_trophy(pmc_id)
    return HttpResponse('Done.', content_type='text/plain')


@csrf_exempt
@require_POST
@api_key_required
@transaction.atomic
def refresh_achievement(request, pmc_id):
    AwardAssignmentService.refresh_achievement(pmc_id)
    return HttpResponse('Done.', content_type='text/plain')


@csrf_exempt
@require_POST
@api_key_required
@transaction.atomic
def refresh_trophies(request):
    AwardAssignmentService.refresh_all_user_trophies()
    return HttpResponse('Done.', content_type='text/plain')


@csrf_exempt
@require_POST
@api_key_required
@transaction.atomic
def refresh_achievements(request):
    pmc_id_min = request.GET.get('pmc_id_min')
    pmc_id_max = request.GET.get('pmc_id_max')
    AwardAssignmentService.refresh_user_achievements(
        pmc_id_min=pmc_id_min,
        pmc_id_max=pmc_id_max
    )
    return HttpResponse('Done.', content_type='text/plain')


@csrf_exempt
@require_POST
@api_key_required
@transaction.atomic
def refresh_badges(request):
    AwardAssignmentService.refresh_user_badges()
    return HttpResponse('Done.', content_type='text/plain')


@csrf_exempt
@require_POST
@api_key_required
def hydrate_result_decks(request):
    results = EventResult.objects.filter(
        uploaded_deck_link__isnull=False,
        uploaded_deck_lookup_attempts__lt=EventResult.max_deck_lookup_attempts
    )[:20]
    for result in results:
        try:
            result.add_deck_by_uploaded_link()
        except Exception:
            pass
    return HttpResponse('Done.', content_type='text/plain')


FINDER_TABLE_PAGE_SIZE = 20
FINDER_MODE_DIGITAL = 'digital'
FINDER_MODE_IN_PERSON = 'in_person'


def parse_event_format_filter(raw_event_format):
    if raw_event_format == PlaygroupQuerySet.UNFORMATTED_EVENT_FORMAT:
        return raw_event_format
    try:
        return int(raw_event_format)
    except (TypeError, ValueError):
        return None


def playgroup_finder(request):
    event_formats = EventFormat.objects.all()
    return render(request, 'pmc/g-finder.html', {
        'event_formats': event_formats,
    })


def playgroup_finder_data(request):
    mappable_venue_links = PlaygroupVenue.objects.filter(
        venue__latitude__isnull=False,
        venue__longitude__isnull=False,
    ).select_related('venue')

    event_format = parse_event_format_filter(request.GET.get('event_format'))

    playgroups = Playgroup.objects.discoverable().with_mappable_venues().annotate_member_count().annotate_next_upcoming_event(
        is_digital=False, event_format=event_format
    ).annotate_recent_activity().select_related('type').prefetch_related(
        Prefetch('playgroup_venues', queryset=mappable_venue_links,
                 to_attr='mappable_venue_links')
    ).order_by('name')

    search = request.GET.get('search', '').strip()
    if search:
        playgroups = playgroups.matching_search(
            search, mappable_venues_only=True)

    upcoming_only = request.GET.get('upcoming_events') == '1'
    if event_format or upcoming_only:
        playgroups = playgroups.hosting_events(
            event_format=event_format,
            upcoming_only=upcoming_only,
            is_digital=False,
        )

    results = [
        serialize_playgroup_for_map(playgroup) for playgroup in playgroups
    ]

    return JsonResponse({
        'playgroups': results,
        'total_count': len(results),
    })


def serialize_playgroup_for_map(playgroup):
    venues_data = [
        {
            'id': link.venue.id,
            'name': link.venue.name,
            'latitude': float(link.venue.latitude),
            'longitude': float(link.venue.longitude),
            'city': link.venue.city or '',
            'state_province': link.venue.state_province or '',
            'is_primary': playgroup.primary_venue_id == link.venue.id,
        }
        for link in playgroup.mappable_venue_links
    ]
    activity_level = get_activity_level(playgroup.events_last_90_days)
    next_event = None
    if playgroup.next_event_date:
        next_event = {
            'date': playgroup.next_event_date.isoformat(),
            'format': playgroup.next_event_format_name,
        }
    return {
        'id': playgroup.id,
        'name': playgroup.name,
        'slug': playgroup.slug,
        'member_count': playgroup.member_count,
        'type': playgroup.type.name if playgroup.type else None,
        'logo_src': playgroup.get_logo_src(),
        'url': reverse('pmc-pg-detail', args=[playgroup.slug]),
        'card_url': reverse('pmc-finder-card', args=[playgroup.slug]),
        'next_event': next_event,
        'activity_level': activity_level.slug if activity_level else None,
        'venues': venues_data,
    }


FINDER_CARD_UPCOMING_EVENT_LIMIT = 3
FINDER_CARD_AVATAR_LIMIT = 5


def playgroup_finder_card(request, slug):
    playgroup = get_object_or_404(
        Playgroup.objects.discoverable()
        .annotate_is_primarily_digital()
        .annotate_recent_activity()
        .select_related('type', 'primary_venue')
        .prefetch_related('venues'),
        slug=slug,
    )
    playgroup.display_venue = get_display_venue(playgroup)
    playgroup.activity_level = get_activity_level(
        playgroup.events_last_90_days)

    upcoming_events = filter_upcoming_events(
        Event.objects.filter(playgroups=playgroup)
    ).select_related('format').order_by('start_date', 'pk')[:FINDER_CARD_UPCOMING_EVENT_LIMIT]

    visible_members = PlaygroupMember.objects.filter(
        playgroup=playgroup,
        is_hidden=False,
        user__pmc_profile__show_playgroups_on_profile=True,
    ).select_related('user__pmc_profile__avatar').order_by('-joined_on')
    visible_member_count = visible_members.count()
    members_shown = list(visible_members[:FINDER_CARD_AVATAR_LIMIT])
    default_avatar = Avatar.objects.filter(pmc_id='001').first()
    member_avatar_srcs = [
        (member.user.pmc_profile.avatar or default_avatar).src
        for member in members_shown
        if member.user.pmc_profile.avatar or default_avatar
    ]

    is_member = request.user.is_authenticated and PlaygroupMember.objects.filter(
        playgroup=playgroup, user=request.user).exists()

    return render(request, 'pmc/_finder-group-card.html', {
        'playgroup': playgroup,
        'upcoming_events': upcoming_events,
        'member_avatar_srcs': member_avatar_srcs,
        'visible_member_count': visible_member_count,
        'hidden_member_avatar_count': visible_member_count - len(members_shown),
        'is_member': is_member,
    })


def playgroup_finder_table(request):
    search = request.GET.get('search', '').strip()
    mode = request.GET.get('mode', '')
    event_format = parse_event_format_filter(request.GET.get('event_format'))
    upcoming_only = request.GET.get('upcoming_events') == '1'
    country = request.GET.get('country', '')
    region = request.GET.get('region', '')

    countries = list(
        Venue.objects.used_by_discoverable_playgroups()
        .exclude(country__isnull=True).exclude(country='')
        .order_by('country').values_list('country', flat=True).distinct()
    )
    if country not in countries:
        country = ''

    regions = []
    if country:
        regions = list(
            Venue.objects.used_by_discoverable_playgroups()
            .filter(country=country)
            .exclude(state_province__isnull=True).exclude(state_province='')
            .order_by('state_province').values_list('state_province', flat=True).distinct()
        )
    if region not in regions:
        region = ''

    playgroups = Playgroup.objects.discoverable().annotate_is_primarily_digital().annotate_member_count().annotate_recent_activity().select_related('type', 'primary_venue').prefetch_related('venues').order_by('name')

    if search:
        playgroups = playgroups.matching_search(search)

    if country:
        playgroups = playgroups.located_in(country, region)

    events_are_digital = None
    if mode == FINDER_MODE_DIGITAL:
        playgroups = playgroups.filter(is_primarily_digital=True)
        events_are_digital = True
    elif mode == FINDER_MODE_IN_PERSON:
        playgroups = playgroups.filter(is_primarily_digital=False)
        events_are_digital = False

    if event_format or upcoming_only:
        playgroups = playgroups.hosting_events(
            event_format=event_format,
            upcoming_only=upcoming_only,
            is_digital=events_are_digital,
        )

    playgroups = playgroups.annotate_next_upcoming_event(
        is_digital=events_are_digital, event_format=event_format)

    paginator = Paginator(playgroups, FINDER_TABLE_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    for playgroup in page_obj:
        playgroup.display_venue = get_display_venue(playgroup)
        playgroup.activity_level = get_activity_level(
            playgroup.events_last_90_days)

    is_partial_request = bool(
        request.htmx and not request.htmx.history_restore_request)

    context = {
        'is_partial_request': is_partial_request,
        'page_obj': page_obj,
        'event_formats': EventFormat.objects.all(),
        'countries': countries,
        'regions': regions,
        'filters': {
            'search': search,
            'mode': mode,
            'event_format': str(event_format or ''),
            'upcoming_events': upcoming_only,
            'country': country,
            'region': region,
        },
    }

    template_name = 'pmc/g-finder-table.html'
    if is_partial_request:
        template_name += '#finder-table-results'
    return render(request, template_name, context)


def get_display_venue(playgroup):
    venues = list(playgroup.venues.all())
    return next(
        (venue for venue in venues if venue.id == playgroup.primary_venue_id),
        venues[0] if venues else None,
    )
