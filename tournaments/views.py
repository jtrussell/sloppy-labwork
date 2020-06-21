from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.views import generic
from django.urls import reverse
from django.forms.models import model_to_dict
from django.contrib.auth.mixins import LoginRequiredMixin
from allauth.account.decorators import login_required
from decks.models import Deck
from register.models import DeckRegistration
from .models import Tournament, TournamentRegistration
from .forms import TournamentForm, make_sign_up_form
import random
import datetime
import csv


class TournamentList(LoginRequiredMixin, generic.ListView):
    template_name = 'tournaments/page-list.html'

    def get_queryset(self):
        qa = Tournament.objects.filter(owner=self.request.user)
        return qa.order_by('-date')


@login_required
def detail(request, pk):
    tournament = get_object_or_404(Tournament, id=pk, owner=request.user)

    t_registrations = tournament.tournament_registrations
    num_players = t_registrations.count()

    num_unverified_players = 0

    # if request.GET.get('show', 'all') == 'unregistered':
    #    players_info = [
    #        info for info in players_info if not info['is_verified']]

    return render(request, 'tournaments/page-detail.html', {
        'num_players': num_players,
        'num_unverified_players': num_unverified_players,
        'tournament': tournament
    })


@login_required
def edit(request, pk):
    tourney = get_object_or_404(Tournament, id=pk, owner=request.user)
    if request.method == 'POST':
        pass
        #form = TournamentForm(request.POST, instance=tourney)
        # if 'delete' in request.POST:
        #    tourney.delete()
        #    return HttpResponseRedirect(reverse('profile'))
        # else:
        #    if form.is_valid():
        #        form.save()
        #        return HttpResponseRedirect(reverse('tournaments-detail', kwargs={'pk': tourney.id}))
    else:
        form = TournamentForm(model_to_dict(tourney))
    return render(request, 'tournaments/page-edit.html', {
        'form': form,
    })


@login_required
def sign_up(request, pk):
    tourney = get_object_or_404(Tournament, id=pk, owner=request.user)
    error_messages = []
    treg = None
    if request.method == 'POST' and 'UNREGISTER' in request.POST:
        TournamentRegistration.objects.filter(
            tournament=tourney, player=request.user).delete()
    elif request.method == 'POST':
        num_decks = tourney.tournament_format.decks_per_player
        reg_ids = [request.POST['deck{}'.format(
            ix)] for ix in range(num_decks)]
        registrations = DeckRegistration.objects.filter(id__in=reg_ids)
        decks = [r.deck for r in registrations]
        treg, treg_created = TournamentRegistration.objects.get_or_create(
            tournament=tourney, player=request.user)
        if not treg_created:
            treg.decks.clear()
        treg.decks.add(*decks)
    else:
        try:
            treg = TournamentRegistration.objects.get(
                tournament=tourney, player=request.user)
        except TournamentRegistration.DoesNotExist:
            treg = None
    form = make_sign_up_form(request.user, tourney)
    return render(request, 'tournaments/page-sign-up.html', {
        'error_messages': error_messages,
        'tournament': tourney,
        'form': form,
        'treg': treg,
    })


@login_required
def register(request, pk):
    tourney = get_object_or_404(Tournament, id=pk)
    return render(request, 'tournaments/page-register.html', {})


@login_required
def add(request):
    if request.method == 'POST':
        form = TournamentForm(request.POST)
        if form.is_valid():
            tourney = form.save(commit=False)
            tourney.owner = request.user
            tourney.save()
            return HttpResponseRedirect(reverse('tournaments-detail', kwargs={'pk': tourney.id}))
    else:
        form = get_new_tourney_form()

    return render(request, 'tournaments/page-new.html', {
        'form': form
    })


def get_new_tourney_form():
    return TournamentForm(initial={
        'name': 'Awesome Tournament #{}'.format(random.randint(1000, 9999)),
        'date': datetime.date.today,
        'tournament_format': 1
    })
