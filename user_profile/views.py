from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from allauth.account.decorators import login_required
from django.forms.models import model_to_dict
from .account_removal import (
    AccountRemovalBlocked, find_account_removal_blockers, remove_user_account,
)
from .forms import DeleteAccountForm, EditUsernameForm, EditUserProfileForm


@login_required
def index(request):
    error_messages = []
    if request.method == 'POST':
        username_form = EditUsernameForm(request.POST, instance=request.user)
        profile_form = EditUserProfileForm(
            request.POST, instance=request.user.profile)
        if username_form.is_valid() and profile_form.is_valid():
            username_form.save()
            username_form.request_email_change_if_changed(request)
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

    return render(request, 'user_profile/index.html', {
        'username_form': username_form,
        'profile_form': profile_form,
        'discord_handle': discord_handle,
        'delete_account_form': DeleteAccountForm(user=request.user),
        'account_removal_blockers': find_account_removal_blockers(request.user),
    })


@login_required
@require_POST
def delete_account(request):
    form = DeleteAccountForm(request.POST, user=request.user)
    if not form.is_valid():
        for error in form.errors['confirm_username']:
            messages.error(request, error)
        return redirect('profile')

    try:
        remove_user_account(request.user)
    except AccountRemovalBlocked as blocked:
        for reason in blocked.reasons:
            messages.error(request, reason)
        return redirect('profile')

    logout(request)
    messages.success(request, _('Your account has been deleted.'))
    return redirect('home')
