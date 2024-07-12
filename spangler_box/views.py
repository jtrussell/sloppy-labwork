from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from .forms import SecretChainLinkResponseFormService, SelectTemplateForm
from .models import SecretChain, SecretChainService
from allauth.account.decorators import login_required
from django.db import transaction


@login_required
def create_from_template(request):
    if request.method == 'POST':
        form = SelectTemplateForm(request.POST)
        if form.is_valid():
            template = form.cleaned_data['template']
            with transaction.atomic():
                chain = SecretChainService.create_from_template(
                    template, request.user)
            return HttpResponseRedirect(reverse('spangler-detail', kwargs={'pk': chain.pk}))
    else:
        form = SelectTemplateForm()
    return render(request, 'spangler_box/page-create-from-template.html', {
        'form': form,
    })


@login_required
def join(request, key):
    if request.method == 'POST':
        chain = SecretChainService.join_chain_by_key(key, request.user)
        return HttpResponseRedirect(reverse('spangler-detail', kwargs={'pk': chain.pk}))
    else:
        secret = SecretChain.objects.get(join_key=key)
        return render(request, 'spangler_box/page-join.html', {
            'secret': secret,
        })


def secret_detail(request, pk):
    secret = SecretChain.objects.get(pk=pk)
    user = request.user

    if not user.is_authenticated or not secret.is_user_secret_player(user):
        return render(request, 'spangler_box/page-spangler-detail-public.html', {
            'object': secret,
        })

    current_link = secret.links.with_response_counts().filter(
        num_responses__lt=2).first()

    form = SecretChainLinkResponseFormService.get_form_for_link(current_link)

    return render(request, 'spangler_box/page-spangler-detail-private.html', {
        'object': secret,
        'current_link': current_link,
        'form': form,
    })
