from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST, require_GET
from functools import wraps

from .models import CountdownTimer
from .forms import TimerCreateForm


def can_modify_timer(view_func):
    @wraps(view_func)
    def wrapper(request, timer_code, *args, **kwargs):
        timer = get_object_or_404(CountdownTimer, code=timer_code)
        if timer.owner is not None and timer.owner != request.user:
            raise PermissionDenied
        request.timer = timer
        return view_func(request, timer_code, *args, **kwargs)
    return wrapper


def _timer_context(timer):
    return {
        'timer': timer,
        'code': timer.code,
        'name': timer.name,
        'state': timer.get_state().value,
        'end_time': timer.end_time.isoformat() if timer.end_time else None,
        'end_time_ms': int(timer.end_time.timestamp() * 1000) if timer.end_time else None,
        'pause_time_remaining_seconds': timer.pause_time_remaining_seconds,
    }


@require_GET
def timer_detail(request, timer_code):
    try:
        timer = CountdownTimer.objects.get(code=timer_code)
    except CountdownTimer.DoesNotExist:
        if request.headers.get('HX-Request'):
            return render(request, 'timekeeper/timer-not-found.html', {'code': timer_code})
        return render(request, 'timekeeper/timer-detail-not-found.html', {'code': timer_code})

    context = _timer_context(timer)

    if request.headers.get('HX-Request'):
        return render(request, 'timekeeper/timer-with-controls.html', context)

    return render(request, 'timekeeper/timer-detail.html', context)


@require_GET
def timer_full_page(request, timer_code):
    try:
        timer = CountdownTimer.objects.get(code=timer_code)
    except CountdownTimer.DoesNotExist:
        if request.headers.get('HX-Request'):
            return render(request, 'timekeeper/timer-not-found.html', {'code': timer_code})
        return render(request, 'timekeeper/timer-full-page-not-found.html', {'code': timer_code})

    context = _timer_context(timer)

    if request.headers.get('HX-Request'):
        return render(request, 'timekeeper/timer-full-page-inner.html', context)

    return render(request, 'timekeeper/timer-full-page.html', context)


def timer_create(request):
    if request.method == 'POST':
        form = TimerCreateForm(request.POST)
        if form.is_valid():
            timer = form.save(commit=False)
            if request.user.is_authenticated:
                timer.owner = request.user
            timer.save()
            context = _timer_context(timer)
            return render(request, 'timekeeper/timer-with-controls.html', context)
    else:
        form = TimerCreateForm()

    context = {'form': form}

    if request.user.is_authenticated:
        my_timers = CountdownTimer.objects.filter(
            owner=request.user
        ).order_by('-created_on')
        paginator = Paginator(my_timers, 20)
        page_number = request.GET.get('page', 1)
        context['my_timers'] = paginator.get_page(page_number)

    return render(request, 'timekeeper/timer-create.html', context)


@require_POST
@can_modify_timer
def timer_start(request, timer_code):
    timer = request.timer
    timer.start()
    context = _timer_context(timer)
    return render(request, 'timekeeper/timer-with-controls.html', context)


@require_POST
@can_modify_timer
def timer_pause(request, timer_code):
    timer = request.timer
    timer.pause()
    context = _timer_context(timer)
    return render(request, 'timekeeper/timer-with-controls.html', context)


@require_POST
@can_modify_timer
def timer_add_time(request, timer_code):
    timer = request.timer
    seconds = int(request.POST.get('seconds', 0))
    timer.add_seconds(seconds)
    context = _timer_context(timer)
    return render(request, 'timekeeper/timer-with-controls.html', context)


@require_POST
@can_modify_timer
def timer_subtract_time(request, timer_code):
    timer = request.timer
    seconds = int(request.POST.get('seconds', 0))
    timer.subtract_seconds(seconds)
    context = _timer_context(timer)
    return render(request, 'timekeeper/timer-with-controls.html', context)


@require_POST
@can_modify_timer
def timer_set_time(request, timer_code):
    timer = request.timer
    seconds = int(request.POST.get('seconds', 0))
    timer.set_time_remaining_seconds(seconds)
    context = _timer_context(timer)
    return render(request, 'timekeeper/timer-with-controls.html', context)


@require_POST
@can_modify_timer
def timer_reset(request, timer_code):
    timer = request.timer
    timer.reset()
    context = _timer_context(timer)
    return render(request, 'timekeeper/timer-with-controls.html', context)


@require_POST
@can_modify_timer
def timer_delete(request, timer_code):
    timer = request.timer
    timer.delete()
    return render(request, 'timekeeper/timer-deleted.html', {})
