from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import generic
from .forms import SelectTemplateForm
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


class SecretDetail(generic.DetailView):
    model = SecretChain
    template_name = 'spangler_box/page-spangler-detail.html'

    def get_template_names(self):
        user = self.request.user
        if user.is_authenticated and self.get_object().is_user_secret_player(user):
            return ['spangler_box/page-spangler-detail-private.html']
        else:
            return ['spangler_box/page-spangler-detail-public.html']

    def get_context_data(self, **kwargs):
        context = super(generic.DetailView, self).get_context_data(**kwargs)
        user = self.request.user
        secret = self.get_object()
        if user.is_authenticated and secret.is_user_secret_player(user):
            context['is_waiting_for_player_two_to_join'] = secret.is_waiting_for_player_two_to_join()
            context['is_user_secret_player'] = secret.is_user_secret_player(
                user)
            context['current_link'] = secret.links.with_response_counts().filter(
                num_responses__lt=2).first()
        return context
