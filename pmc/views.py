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
from django.db.models import Sum, Count
from django.http import HttpResponse, HttpResponseRedirect
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
from pmc.forms import EventForm, EventUpdateForm, LeaderboardSeasonPeriodForm, PlaygroupForm, PlaygroupJoinRequestForm, PmcProfileForm
from pmc.forms import PlaygroupMemberForm
from user_profile.forms import EditUsernameForm
from .models import AchievementTier, Badge, EventResult, LeaderboardLog, LeaderboardSeasonPeriod, PlaygroupJoinRequest, UserAchievementTier, UserBadge, Trophy, UserTrophy, Achievement
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
from .models import RankingPointsMap
from .models import AwardAssignmentService


def is_pg_member(view):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
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


def api_key_required(view):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            api_key = request.META.get('HTTP_X_API_KEY')
            if api_key == os.environ['PMC_RATINGS_API_KEY']:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return wrapper
    return decorator(view)


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
    if request.method == 'POST':
        form = PlaygroupForm(
            request.POST, instance=Playgroup.objects.get(slug=slug))
        if form.is_valid():
            pg = form.save()
            return HttpResponseRedirect(reverse('pmc-pg-detail', kwargs={'slug': pg.slug}))
    else:
        form = PlaygroupForm(instance=Playgroup.objects.get(slug=slug))

    context = {
        'form': form,
        'join_requests': PlaygroupJoinRequest.objects.filter(
            playgroup__slug=slug,
            status=PlaygroupJoinRequest.RequestStatuses.SUBMITTED
        )
    }
    return render(request, 'pmc/pg-manage.html', context)


@login_required
def my_results(request):
    return render(request, 'pmc/g-my-results.html', {
        'results': EventResult.objects.filter(user=request.user).order_by('-event__start_date')
    })


@login_required
def my_keychain(request):
    profile = request.user.pmc_profile
    current_level = profile.get_level()
    next_level = profile.get_next_level()
    level_up_info = profile._get_level_up_info()
    my_results = profile.get_events()

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
        )
    })


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
            return HttpResponseRedirect(reverse('pmc-pg-member-detail', kwargs={
                'slug': slug,
                'username': member.user.username
            }))

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
        return super().dispatch(request, *args, **kwargs)


class PlaygroupMemberDetail(LoginRequiredMixin, generic.DetailView):
    model = PlaygroupMember
    template_name = 'pmc/pg-member-detail.html'

    @method_decorator(login_required)
    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return PlaygroupMember.objects.get(
            user__username=self.kwargs['username'],
            playgroup__slug=self.kwargs['slug']
        )


@login_required
@is_pg_staff
def playgroup_member_manage(request, slug, username):
    member = get_object_or_404(
        PlaygroupMember,
        user__username=username,
        playgroup__slug=slug
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'assign_badge':
            pk = request.POST.get('badge_id')
            badge = get_object_or_404(Badge, pk=pk)
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
        print('event not found')
        return render(request, 'pmc/g-event-not-found.html')


class EventDetail(LoginRequiredMixin, generic.DetailView):
    model = Event
    template_name = 'pmc/pg-event-detail.html'

    @method_decorator(login_required)
    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


@login_required
@is_pg_staff
def manage_event(request, slug, pk):
    event = get_object_or_404(Event, pk=pk)
    if request.method == 'POST':
        form = EventUpdateForm(request.POST, instance=event)
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
        form = EventUpdateForm(instance=event)
    context = {'object': event, 'form': form}
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
    if pk is None:
        return HttpResponseRedirect(reverse('pmc-pg-leaderboard', kwargs={
            'slug': slug,
            'pk': Leaderboard.objects.first().pk
        }))
    rank_filters = {
        'leaderboard': pk,
        'playgroup__slug': slug
    }
    season_period_form = LeaderboardSeasonPeriodForm(
        Leaderboard.objects.get(pk=pk), request.GET or None)
    try:
        # TODO - determine season/period and send that into the form instead
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
        'leaderboards': Leaderboard.objects.all(),
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

    rank_filters = {
        'leaderboard': pk,
        'playgroup': None
    }
    season_period_form = LeaderboardSeasonPeriodForm(
        Leaderboard.objects.get(pk=pk), request.GET or None)
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
        form = EventForm(request.POST, request.FILES)
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
                    'user', 'finishing_position', 'num_wins', 'num_losses']
                if not set(reader.fieldnames).issubset(set(available_headers)):
                    form_errors.append(
                        'Your results file may include only these columns: {columns}'.format(
                            columns=', '.join(available_headers))
                    )
                elif not 'user' in reader.fieldnames:
                    form_errors.append(
                        'Your results file must include a "user" column')
                else:
                    User = get_user_model()
                    for row in reader:
                        username = row.pop('user')
                        row = {key: (None if value == '' else value)
                               for key, value in row.items()}
                        try:
                            user = User.objects.get(username=username)
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
        form = EventForm()
    return render(request, 'pmc/pg-submit-event-results.html', {
        'form_errors': form_errors,
        'form': form,
    })


def typography(request):
    return render(request, 'pmc/typography.html')


def about(request):
    return render(request, 'pmc/about.html')


def about_ranking_points(request):
    return render(request, 'pmc/g-about-ranking-points.html', {
        'ranges_by_size': [
            ('3 Players', RankingPointsMap.list_points_for_fp_ranges(3)),
            ('4 Players', RankingPointsMap.list_points_for_fp_ranges(4)),
            ('5 to 8 Players', RankingPointsMap.list_points_for_fp_ranges(8)),
            ('9 to 16 Players', RankingPointsMap.list_points_for_fp_ranges(16)),
            ('17 to 32 Players', RankingPointsMap.list_points_for_fp_ranges(32)),
            ('32 to 64 Players', RankingPointsMap.list_points_for_fp_ranges(64)),
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
        # TODO verify that the event is associated with the playgroup
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
                user=User.objects.get(username=username),
                event=event,
                **result_data
            )
            result.event = event
            result.save()
            RankingPointsService.assign_points_for_event(event)
            messages.success(request, _('Result added.'))
        except User.DoesNotExist:
            messages.error(request, _(
                'Oops! We could not find a user named {}. Usernames are case sensitive.'.format(username)))
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


@csrf_exempt
@require_POST
@api_key_required
@transaction.atomic
def refresh_leaderboard(request, pk):
    leaderboard = Leaderboard.objects.get(pk=pk)
    period = leaderboard.get_period_for_date(date.today())
    if leaderboard.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.MONTH:
        top_n = 4
        order_by = 'total_points'
    elif leaderboard.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.SEASON:
        top_n = 10
        order_by = 'total_points'
    elif leaderboard.period_frequency == LeaderboardSeasonPeriod.FrequencyOptions.ALL_TIME:
        top_n = 100
        order_by = 'total_points'
    else:
        raise ValueError('Invalid leaderboard period frequency')

    RankingPointsService.assign_points_for_leaderboard(
        leaderboard,
        period,
        order_by=order_by,
        top_n=top_n
    )

    last_week_period = leaderboard.get_period_for_date(
        date.today() - timedelta(days=7))
    if last_week_period.pk != period.pk:
        RankingPointsService.assign_points_for_leaderboard(
            leaderboard,
            last_week_period,
            order_by=order_by,
            top_n=top_n
        )

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
        if form.is_valid() and username_form.is_valid():
            form.save()
            username_form.save()
            messages.success(request, _('Profile updated.'))
            return HttpResponseRedirect(reverse('pmc-my-keychain-manage'))
        else:
            messages.error(request, _(
                'Oops! That\'s not quite right. Check the form and try again.'))

    else:
        form = PmcProfileForm(instance=profile)
        username_form = EditUsernameForm(
            instance=request.user)

    return render(request, 'pmc/g-me-manage.html', {
        'form': form,
        'username_form': username_form,
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
        print(e)
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
def add_pg_member_by_username(request, slug):
    username = request.POST.get('username').strip()
    try:
        User = get_user_model()
        member, created = PlaygroupMember.objects.get_or_create(
            playgroup=Playgroup.objects.get(slug=slug),
            user=User.objects.get(username=username)
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
            'Oops! We could not find a user with that username. Usernames are case sensitive.'))
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
    writer.writerow(['user', 'finishing_position', 'num_wins', 'num_losses'])
    members = PlaygroupMember.objects.filter(playgroup__slug=slug)
    for member in members:
        writer.writerow([member.user.username, '', '', ''])
    return response


@login_required
def my_awards(request):
    context = {
        'badges': Badge.with_user_badges(request.user).all(),
        'achievements': Achievement.with_highest_user_achievements_tier(request.user).all(),
        'trophies': Trophy.with_user_trophies(request.user).all(),
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
            request.user, achievement.criteria),
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
    AwardAssignmentService.refresh_user_achievements()
    return HttpResponse('Done.', content_type='text/plain')
