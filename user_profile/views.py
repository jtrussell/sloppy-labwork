from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect, render
from allauth.account.decorators import login_required
from django.forms.models import model_to_dict
from register.models import DeckRegistration
from .forms import EditUsernameForm, EditUserProfileForm


@login_required
def index(request):
    error_messages = []
    if request.method == 'POST':
        username_form = EditUsernameForm(request.POST, instance=request.user)
        profile_form = EditUserProfileForm(
            request.POST, instance=request.user.profile)
        if username_form.is_valid() and profile_form.is_valid():
            username_form.save()
            profile_form.save()
            messages.success(
                request, _('Your profile has been updated.'))
            return redirect('profile')

        else:
            messages.error(
                request, _('Your profile could not be updated, please check for any errors in the form below.'))
    else:
        username_form = EditUsernameForm()
        username_form.initial = model_to_dict(request.user)
        profile_form = EditUserProfileForm()
        profile_form.initial = model_to_dict(request.user.profile)

    discord_handle = request.user.profile.discord_handle

    my_registrations = DeckRegistration.objects.filter(user=request.user)
    my_registrations = my_registrations.filter(
        Q(status=DeckRegistration.Status.VERIFIED_ACTIVE) | Q(status=DeckRegistration.Status.PENDING))

    num_registrations = len(my_registrations)
    my_pending_registrations = my_registrations.filter(
        status=DeckRegistration.Status.PENDING)
    num_pending_registrations = len(my_pending_registrations)

    return render(request, 'user_profile/index.html', {
        'username_form': username_form,
        'profile_form': profile_form,
        'discord_handle': discord_handle,
        'num_registrations': num_registrations,
        'num_pending_registrations': num_pending_registrations
    })
