import csv
from django.db import transaction
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.contrib.auth import get_user_model
from pmc.forms import EventForm
from .models import EventResult, Playgroup, PlaygroupEvent
from .models import PlaygroupMember
from .models import Event


def is_pg_member(view):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            is_member = PlaygroupMember.objects.filter(
                user=request.user, playgroup__slug=kwargs['slug']).exists()
            if is_member:
                return view_func(request, *args, **kwargs)
            return HttpResponse(status=401)
        return wrapper
    return decorator(view)


def is_pg_staff(view):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            is_member = PlaygroupMember.objects.filter(
                user=request.user, playgroup__slug=kwargs['slug'], is_staff=True).exists()
            if is_member:
                return view_func(request, *args, **kwargs)
            return HttpResponse(status=401)
        return wrapper
    return decorator(view)


class PlaygroupDetail(generic.DetailView):
    model = Playgroup
    template_name = 'pmc/pg-detail.html'

    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


@is_pg_member
def my_playgroup_profile(request, slug):
    return render(request, 'pmc/pg-me.html', {
        'slug': slug,
        'events': Event.objects.filter(
            playgroups__slug=slug,
            results__user=request.user
        )
    })


@is_pg_member
def manage_my_playgroup_profile(request, slug):
    return render(request, 'pmc/pg-me-manage.html', {
        'slug': slug,
    })


class PlaygroupMembersList(generic.ListView):
    context_object_name = 'members'
    template_name = 'pmc/pg-members.html'

    def get_queryset(self):
        return PlaygroupMember.objects.filter(playgroup__slug=self.kwargs['slug'])

    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class PlaygroupMemberDetail(generic.DetailView):
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


class PlaygroupMemberManage(generic.DetailView):
    model = PlaygroupMember
    template_name = 'pmc/pg-member-manage.html'

    @method_decorator(is_pg_staff)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class PlaygroupEventsList(generic.ListView):
    context_object_name = 'events'
    template_name = 'pmc/pg-events.html'

    def get_queryset(self):
        return Event.objects.filter(playgroups__slug=self.kwargs['slug'])

    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class EventDetail(generic.DetailView):
    model = Event
    template_name = 'pmc/event-detail.html'

    @method_decorator(is_pg_member)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


@is_pg_member
def playgroup_leaderboard(request, slug):
    return render(request, 'pmc/pg-leaderboard.html', {'slug': slug})


# Leaving some big TODO items here:
#  - Error handling for when a user is not found
#  - Need to think through how we allow users in the results that don't belong
#    an associated PG.
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
                EventResult.objects.bulk_create(event_results)
                PlaygroupEvent.objects.create(
                    playgroup=Playgroup.objects.get(slug=slug),
                    event=event
                )
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


def event_manage(request, pk):
    return render(request, 'pmc/event-manage.html', {'pk': pk})
