import json
from math import e
import os
import csv
from datetime import date
from datetime import timedelta
from re import U
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.contrib.auth.mixins import LoginRequiredMixin
from pmc.context_processors import playgroup
from pmc.forms import EventForm, LeaderboardSeasonPeriodForm, PlaygroupForm, PmcProfileForm
from pmc.forms import PlaygroupMemberForm
from .models import EventResult, LeaderboardLog, LeaderboardSeason, LeaderboardSeasonPeriod
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


class PlaygroupDetail(LoginRequiredMixin, generic.DetailView):
    model = Playgroup
    template_name = 'pmc/pg-detail.html'

    @method_decorator(login_required)
    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


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
    return render(request, 'pmc/pg-manage.html', {
        'form': form,
    })


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

    @method_decorator(is_pg_staff)
    def post(self, request, *args, **kwargs):
        member = self.get_object()
        action = request.POST.get('action')
        if action == 'remove':
            member.delete()
            messages.success(request, _('Member removed.'))
            return HttpResponseRedirect(reverse('pmc-pg-members', kwargs={'slug': kwargs['slug']}))


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
    print(pk)
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
    template_name = 'pmc/event-detail.html'

    @method_decorator(login_required)
    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


@require_POST
@login_required
@is_pg_staff
def delete_event(request, slug, pk):
    event = get_object_or_404(Event, pk=pk)
    # TODO - ensure that the event is associated with the playgroup
    event.delete()
    messages.success(request, _('Event deleted.'))
    return HttpResponseRedirect(reverse('pmc-pg-events', kwargs={'slug': slug}))


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

    return render(request, 'pmc/pg-leaderboard.html', {
        'leaderboards': Leaderboard.objects.all(),
        'season_period_form': season_period_form,
        'rankings': PlayerRank.objects.filter(**rank_filters),
        'slug': slug,
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

    return render(request, 'pmc/g-leaderboard.html', {
        'leaderboards': Leaderboard.objects.all(),
        'season_period_form': season_period_form,
        'rankings': PlayerRank.objects.filter(**rank_filters),
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
            csv_file = form.cleaned_data['results_file']
            decoded_file = csv_file.read().decode('utf-8')
            reader = csv.DictReader(decoded_file.splitlines())
            available_headers = [
                'user', 'finishing_position', 'num_wins', 'num_losses']
            if not set(reader.fieldnames).issubset(set(available_headers)):
                form_errors.append(
                    f'Your results file may include only these columns: {
                        ', '.join(available_headers)}'
                )
            elif not 'user' in reader.fieldnames:
                form_errors.append(
                    f'Your results file must include a "user" column')
            else:
                event = form.save()
                User = get_user_model()
                event_results = []
                for row in reader:
                    username = row.pop('user')
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
                results = EventResult.objects.bulk_create(event_results)

                RankingPointsService.assign_points_for_results(
                    results,
                    event.player_count or len(results)
                )

                PlaygroupEvent.objects.create(
                    playgroup=Playgroup.objects.get(slug=slug),
                    event=event
                )

                messages.success(request, _('Event results added.'))
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


@login_required
def event_manage(request, pk):
    return render(request, 'pmc/event-manage.html', {'pk': pk})


def typography(request):
    return render(request, 'pmc/typography.html')


def about(request):
    return render(request, 'pmc/about.html')


def about_ranking_points(request):
    return render(request, 'pmc/g-about-ranking-points.html', {
        'ranges_by_size': [
            ('Up to 4 Players', RankingPointsMap.list_points_for_fp_ranges(4)),
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
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('pmc-my-keychain'))

    else:
        form = PmcProfileForm(instance=profile)

    return render(request, 'pmc/g-me-manage.html', {
        'form': form,
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
        messages.success(request, _('Member added.'))
        return HttpResponseRedirect(reverse('pmc-pg-member-detail', kwargs={
            'slug': slug,
            'username': member.user.username
        }))
    except Exception as e:
        print(e)
        messages.error(request, _('Oops! Something went wrong.'))
    return HttpResponseRedirect(reverse('pmc-pg-members', kwargs={'slug': slug}))


@require_POST
@login_required
@is_pg_staff
def add_pg_member_by_username(request, slug):
    username = request.POST.get('username')
    try:
        User = get_user_model()
        member, _created = PlaygroupMember.objects.get_or_create(
            playgroup=Playgroup.objects.get(slug=slug),
            user=User.objects.get(username=username)
        )
        messages.success(request, _('Member added.'))
        return HttpResponseRedirect(reverse('pmc-pg-member-detail', kwargs={
            'slug': slug,
            'username': member.user.username
        }))
    except User.DoesNotExist:
        messages.error(request, _(
            'Oops! We could not find a user with that username. Usernames are case sensitive.'))
    except Exception as e:
        print(e)
        messages.error(request, _('Oops! Something went wrong.'))
    return HttpResponseRedirect(reverse('pmc-pg-members', kwargs={'slug': slug}))
