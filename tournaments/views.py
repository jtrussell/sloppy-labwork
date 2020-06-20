from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.views import generic
from django.urls import reverse
from django.forms.models import model_to_dict
from django.contrib.auth.mixins import LoginRequiredMixin
from allauth.account.decorators import login_required
from register.models import DeckRegistration
from .models import Tournament
from .forms import TournamentForm
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
    tournament = get_object_or_404(Tournament, id=pk)
    players_info = tournament.parse_players_info()

    # Need to look up registrations for each player/deck combo :/
    # This is kinda gross... should probably just refactor this to have better
    # models for the situation
    deck_ids = [info['deck_id'] for info in players_info]
    registrations = DeckRegistration.objects.filter(
        deck__in=deck_ids, is_verified=True, is_active=True)

    deck_to_discords_map = {deck_id: [] for deck_id in deck_ids}
    for reg in registrations:
        deck_to_discords_map[str(reg.deck.id)].append(
            reg.user.profile.discord_handle)

    for info in players_info:
        deck_id = info['deck_id']
        discords_linked_to_deck = deck_to_discords_map[deck_id]
        discord_handle = info['discord_handle']
        info['is_verified'] = discord_handle in discords_linked_to_deck

    num_players = len(players_info)
    num_unregistered_players = len(
        [info for info in players_info if not info['is_verified']])

    if request.GET.get('show', 'all') == 'unregistered':
        players_info = [
            info for info in players_info if not info['is_verified']]

    return render(request, 'tournaments/page-detail.html', {
        'num_players': num_players,
        'num_unregistered_players': num_unregistered_players,
        'tournament': tournament,
        'players_info': players_info,
    })


class TournamentEdit(LoginRequiredMixin, generic.DetailView):
    model = Tournament
    template_name = 'tournaments/page-edit.html'


@login_required
def edit(request, pk):
    tourney = get_object_or_404(Tournament, id=pk)
    if request.method == 'POST':
        form = TournamentForm(request.POST, instance=tourney)
        if 'delete' in request.POST:
            tourney.delete()
            return HttpResponseRedirect(reverse('profile'))
        else:
            if form.is_valid():
                form.save()
                return HttpResponseRedirect(reverse('tournaments-detail', kwargs={'pk': tourney.id}))
    else:
        form = TournamentForm(model_to_dict(tourney))
    return render(request, 'tournaments/page-edit.html', {
        'form': form,
    })


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
        'players_info': '\n'.join([
            '\t'.join(['discord_handle', 'challonge_handle',
                        'tco_handle', 'master_vault_link']),
            '\t'.join(['yurk#4332', 'yurk_challonge',
                       'yurk_tco', 'https://decksofkeyforge.com/decks/f80d1517-76f7-4338-b1b3-74d09629687f']),
            '\t'.join(['jtrussell#4520', 'jtrussell',
                       'jtrussell', 'https://www.keyforgegame.com/deck-details/d198df7c-ac63-46a9-9c92-3e56dcc56773']),
        ])
    })
