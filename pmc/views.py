import os
import csv
from django.core.exceptions import PermissionDenied
from django.db import transaction
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
from pmc.forms import EventForm
from pmc.forms import PlaygroupMemberForm
from .models import EventResult, LeaderboardLog
from .models import PlayerRank
from .models import Leaderboard
from .models import Playgroup
from .models import PlaygroupEvent
from .models import PlaygroupMember
from .models import Event
from .models import RankingPointsService


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

    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


@login_required
@is_pg_member
def my_playgroup_profile(request, slug):
    return render(request, 'pmc/pg-me.html', {
        'slug': slug,
        'events': Event.objects.filter(
            playgroups__slug=slug,
            results__user=request.user
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
            return HttpResponseRedirect(reverse('pmc-my-pg', kwargs={'slug': slug}))

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
        return PlaygroupMember.objects.filter(playgroup__slug=self.kwargs['slug'])

    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class PlaygroupMemberDetail(LoginRequiredMixin, generic.DetailView):
    model = PlaygroupMember
    template_name = 'pmc/pg-member-detail.html'

    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return PlaygroupMember.objects.get(
            user__username=self.kwargs['username'],
            playgroup__slug=self.kwargs['slug']
        )


class PlaygroupMemberManage(LoginRequiredMixin, generic.DetailView):
    model = PlaygroupMember
    template_name = 'pmc/pg-member-manage.html'

    @method_decorator(is_pg_staff)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class PlaygroupEventsList(LoginRequiredMixin, generic.ListView):
    context_object_name = 'events'
    template_name = 'pmc/pg-events.html'

    def get_queryset(self):
        return Event.objects.filter(playgroups__slug=self.kwargs['slug'])

    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class EventDetail(LoginRequiredMixin, generic.DetailView):
    model = Event
    template_name = 'pmc/event-detail.html'

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
    return render(request, 'pmc/pg-leaderboard.html', {
        'leaderboards': Leaderboard.objects.all(),
        'rankings': PlayerRank.objects.filter(leaderboard=pk, playgroup__slug=slug),
        'slug': slug,
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
                return HttpResponseRedirect(reverse('pmc-event-detail', kwargs={
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

@require_POST
@login_required
@is_pg_staff
def assign_event_points(request, slug, pk):
    event = get_object_or_404(Event, pk=pk)
    # TODO verify that the event is associated with the playgroup
    RankingPointsService.assign_points_for_event(event)
    return HttpResponseRedirect(reverse('pmc-event-detail', kwargs={'slug': slug, 'pk': pk}))


@csrf_exempt
@require_POST
@api_key_required
@transaction.atomic
def refresh_leaderboard(request, pk):
    leaderboard = Leaderboard.objects.get(pk=pk)
    period = leaderboard.get_current_period()
    RankingPointsService.assign_points_for_leaderboard(
        leaderboard,
        period
    )
    LeaderboardLog.objects.create(
        leaderboard=leaderboard
    ).save()
    return HttpResponse('Done.', content_type='text/plain')
