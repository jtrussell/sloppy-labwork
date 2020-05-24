from datetime import datetime
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from allauth.account.decorators import login_required
from requests import get
from decks.models import Deck
from .forms import RegiseterNewDeckForm
from .models import DeckRegistration


def index(request):
    return render(request, 'register/page-home.html', {})


@login_required
def add(request):
    if request.method == 'POST':
        form = RegiseterNewDeckForm(request.POST)
        if form.is_valid():
            # Process the form...
            master_vault_url = form.cleaned_data['master_vault_link']
            master_vault_id = Deck.get_id_from_master_vault_url(
                master_vault_url)

            deck, created = Deck.objects.get_or_create(id=master_vault_id)
            if created:
                r = get(deck.get_master_vault_url())
                deck.name = r.json()['data']['name']
                deck.save()
            else:
                old_registrations = DeckRegistration.objects.filter(
                    user=request.user,
                    deck=deck,
                    has_photo_verification=False
                )
                old_registrations.delete()

            # Save the uploaded image

            # Save the registration
            registration = DeckRegistration()
            registration.user = request.user
            registration.deck = deck
            registration.save()

            # Better to redirect to the deck's registration page
            return HttpResponseRedirect(reverse('register-add-success'))
    else:
        form = RegiseterNewDeckForm()

    return render(request, 'register/page-new.html', {'form': form})


@login_required
def edit(request):
    return render(request, 'regiseter/page-new.html', {})


@staff_member_required
def verify(request, id):
    registration = DeckRegistration.objects.get(id=id)
    registration.has_photo_verification = True
    registration.verified_by = request.user
    registration.verified_on = datetime.now()
    registration.save()
    return HttpResponseRedirect('/admin/register/deckregistration/')
