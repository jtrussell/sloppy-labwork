from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db import models
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils.translation import gettext_lazy as _
import json

from .models import (
    Tournament, Player, TournamentAdmin, Stage, StagePlayer, Round,
    Match, MatchResult, TournamentActionLog, StandingCalculator,
    get_pairing_strategy
)
from .forms import TournamentForm, PlayerForm, StageForm, MatchResultForm, PlayerRegistrationForm


def is_tournament_admin(view_func):
    def wrapper(request, tournament_id, *args, **kwargs):
        tournament = get_object_or_404(Tournament, id=tournament_id)
        if not tournament.is_user_admin(request.user):
            raise PermissionDenied
        return view_func(request, tournament_id, *args, **kwargs)
    return wrapper


def is_tournament_admin_or_player(view_func):
    def wrapper(request, tournament_id, *args, **kwargs):
        tournament = get_object_or_404(Tournament, id=tournament_id)
        if not (tournament.is_user_admin(request.user) or
                tournament.players.filter(user=request.user).exists()):
            raise PermissionDenied
        return view_func(request, tournament_id, *args, **kwargs)
    return wrapper


def redirect_to(request, url):
    """Redirect to a URL, using HTMX if available."""
    if request.htmx:
        resp = HttpResponse(url)
        resp['HX-Redirect'] = url
        return resp
    return HttpResponseRedirect(url)


@login_required
def my_tournaments(request):
    admin_tournaments = Tournament.objects.filter(
        models.Q(owner=request.user) |
        models.Q(tournament_admins__user=request.user)
    ).distinct().order_by('-created_on')

    player_tournaments = Tournament.objects.filter(
        players__user=request.user
    ).order_by('-created_on')

    admin_paginator = Paginator(admin_tournaments, 10)
    player_paginator = Paginator(player_tournaments, 10)

    admin_page = request.GET.get('admin_page', 1)
    player_page = request.GET.get('player_page', 1)

    admin_tournaments_page = admin_paginator.get_page(admin_page)
    player_tournaments_page = player_paginator.get_page(player_page)

    context = {
        'admin_tournaments': admin_tournaments_page,
        'player_tournaments': player_tournaments_page,
    }
    return render(request, 'tourney/my-tournaments.html', context)


@login_required
def create_tournament(request):
    if request.method == 'POST':
        form = TournamentForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                tournament = form.save(commit=False)
                tournament.owner = request.user
                tournament.save()

                # Create main stage
                main_stage = tournament.create_initial_stage(
                    main_pairing_strategy=form.cleaned_data['main_pairing_strategy'],
                    main_max_players=form.cleaned_data['main_max_players']
                )

                # Set ranking criteria for main stage
                ranking_criteria = form.cleaned_data.get(
                    'ranking_criteria_json', [])
                if ranking_criteria:
                    main_stage.set_ranking_criteria(ranking_criteria)

                # Create playoff stage if enabled
                if form.cleaned_data['enable_playoffs']:
                    tournament.create_playoff_stage(
                        max_players=form.cleaned_data['playoff_max_players']
                    )

                TournamentActionLog.objects.create(
                    tournament=tournament,
                    user=request.user,
                    action_type=TournamentActionLog.ActionType.CREATE_TOURNAMENT,
                    description=f'Tournament "{tournament.name}" created'
                )

            messages.success(
                request, f'Tournament "{tournament.name}" created successfully!')
            return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_id': tournament.id}))
    else:
        form = TournamentForm()

    return render(request, 'tourney/create-tournament.html', {'form': form})


@login_required
@is_tournament_admin
def edit_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)

    if request.method == 'POST':
        form = TournamentForm(request.POST, instance=tournament)
        if form.is_valid():
            with transaction.atomic():
                form.save()

                # Update main stage
                main_stage = tournament.stages.filter(order=1).first()
                if main_stage:
                    main_stage.pairing_strategy = form.cleaned_data['main_pairing_strategy']
                    main_stage.max_players = form.cleaned_data['main_max_players']

                    # Update ranking criteria for main stage
                    ranking_criteria = form.get_ranking_criteria_from_post(
                        request.POST)
                    main_stage.set_ranking_criteria(ranking_criteria)

                    main_stage.save()
                else:
                    # Create main stage if it doesn't exist
                    main_stage = tournament.create_initial_stage(
                        main_pairing_strategy=form.cleaned_data['main_pairing_strategy'],
                        main_max_players=form.cleaned_data['main_max_players']
                    )

                    # Set ranking criteria for new main stage
                    ranking_criteria = form.get_ranking_criteria_from_post(
                        request.POST)

                    main_stage.set_ranking_criteria(ranking_criteria)

                # Handle playoff stage
                playoff_stage = tournament.stages.filter(order=2).first()
                if form.cleaned_data['enable_playoffs']:
                    if playoff_stage:
                        playoff_stage.max_players = form.cleaned_data['playoff_max_players']
                        playoff_stage.save()
                    else:
                        tournament.create_playoff_stage(
                            max_players=form.cleaned_data['playoff_max_players']
                        )
                elif playoff_stage:
                    # Remove playoff stage if it exists but is disabled
                    playoff_stage.delete()

            messages.success(request, 'Tournament updated successfully!')
            return redirect_to(request, reverse('tourney-edit-tournament', kwargs={'tournament_id': tournament.id}))
    else:
        form = TournamentForm(instance=tournament)

    # Get available criteria for the template
    from .models import get_available_ranking_criteria
    available_criteria = get_available_ranking_criteria()

    # Get current main stage criteria for JavaScript initialization
    main_stage = tournament.stages.filter(order=1).first()
    current_criteria = []
    if main_stage:
        current_criteria = main_stage.get_ranking_criteria()

    context = {
        'form': form,
        'tournament': tournament,
        'available_criteria': available_criteria,
        'current_criteria_json': json.dumps(current_criteria)
    }
    return render(request, 'tourney/edit-tournament.html', context)


def get_tournament_base_context(request, tournament):
    current_stage = tournament.get_current_stage()
    current_round = current_stage.get_current_round() if current_stage else None

    is_admin = tournament.is_user_admin(request.user)

    player = None
    is_player = False
    is_active_player = False
    is_dropped_player = False

    if request.user.is_authenticated:
        try:
            player = tournament.players.get(user=request.user)
            is_player = True
            is_active_player = player.status == Player.PlayerStatus.ACTIVE
            is_dropped_player = player.status == Player.PlayerStatus.DROPPED
        except Player.DoesNotExist:
            pass

    can_create_round = False
    can_start_next_stage = False
    can_delete_latest_round = False
    next_stage = None
    if is_admin:
        can_create_round = tournament.can_create_round_in_current_stage()
        can_start_next_stage = tournament.can_start_next_stage()
        next_stage = tournament.get_next_stage()

        if current_stage:
            latest_round = current_stage.rounds.order_by('-order').first()
            can_delete_latest_round = latest_round is not None

    # Get user's pending matches across all stages/rounds (only for active players)
    pending_matches = []
    if request.user.is_authenticated and is_active_player:
        # Find all stage players for this user in this tournament
        user_stage_players = StagePlayer.objects.filter(
            player__tournament=tournament,
            player__user=request.user,
            player__status=Player.PlayerStatus.ACTIVE
        )

        if user_stage_players.exists():
            # Find all pending matches for this user
            pending_matches = Match.objects.filter(
                models.Q(player_one__in=user_stage_players) |
                models.Q(player_two__in=user_stage_players),
                result__isnull=True,  # No result yet = pending
                player_two__isnull=False  # Exclude byes
            ).select_related(
                'round__stage',
                'player_one__player',
                'player_two__player'
            ).order_by('round__stage__order', 'round__order')

    return {
        'tournament': tournament,
        'stages': tournament.stages.all(),
        'is_admin': is_admin,
        'is_player': is_player,
        'is_active_player': is_active_player,
        'is_dropped_player': is_dropped_player,
        'player': player,
        'can_create_round': can_create_round,
        'can_start_next_stage': can_start_next_stage,
        'can_delete_latest_round': can_delete_latest_round,
        'next_stage': next_stage,
        'current_stage': current_stage,
        'current_round': current_round,
        'pending_matches': pending_matches,
        'user': request.user,
    }


@login_required
@is_tournament_admin_or_player
def tournament_detail_home(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    context = get_tournament_base_context(request, tournament)
    context['current_tab'] = 'home'

    # Get user's pending matches for home tab
    user_matches = []
    if context['is_active_player'] and context['current_round']:
        user_stage_player = context['current_stage'].stage_players.filter(
            player__user=request.user,
            player__status=Player.PlayerStatus.ACTIVE).first()
        if user_stage_player:
            user_matches = context['current_round'].matches.filter(
                models.Q(player_one=user_stage_player) | models.Q(
                    player_two=user_stage_player)
            ).filter(result__isnull=True)

    context['user_matches'] = user_matches

    if request.htmx:
        return render(request, 'tourney/partials/tournament-detail-home-content.html', context)
    return render(request, 'tourney/tournament-detail-home.html', context)


@login_required
@is_tournament_admin_or_player
def tournament_detail_matches(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    context = get_tournament_base_context(request, tournament)
    context['current_tab'] = 'matches'

    selected_stage_id = request.GET.get('stage')
    selected_round_id = request.GET.get('round')

    if selected_stage_id:
        selected_stage = get_object_or_404(
            Stage, id=selected_stage_id, tournament=tournament)
    else:
        selected_stage = context['current_stage']

    if selected_round_id and selected_stage:
        selected_round = get_object_or_404(
            Round, id=selected_round_id, stage=selected_stage)
        matches = selected_round.matches.all()
    elif selected_stage:
        latest_round = selected_stage.rounds.order_by('-order').first()
        selected_round = latest_round
        matches = latest_round.matches.all() if latest_round else []
    else:
        selected_round = None
        matches = []

    context.update({
        'selected_stage': selected_stage,
        'selected_round': selected_round,
        'matches': matches,
    })

    if request.htmx:
        return render(request, 'tourney/partials/tournament-detail-matches-content.html', context)
    return render(request, 'tourney/tournament-detail-matches.html', context)


@login_required
@is_tournament_admin_or_player
def tournament_detail_standings(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    context = get_tournament_base_context(request, tournament)
    context['current_tab'] = 'standings'

    standings = []
    enabled_criteria = []
    if context['current_stage']:
        standings = StandingCalculator.get_stage_standings(
            context['current_stage'])
        enabled_criteria = context['current_stage'].get_enabled_ranking_criteria_objects(
        )

    context['standings'] = standings
    context['enabled_criteria'] = enabled_criteria

    if request.htmx:
        return render(request, 'tourney/partials/tournament-detail-standings-content.html', context)
    return render(request, 'tourney/tournament-detail-standings.html', context)


@login_required
@is_tournament_admin
def manage_players(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_player':
            form = PlayerForm(request.POST)
            if form.is_valid():
                try:
                    player = form.save(commit=False)
                    player.tournament = tournament
                    player.save()

                    current_stage = tournament.get_current_stage()
                    if current_stage:
                        max_seed = current_stage.stage_players.aggregate(
                            models.Max('seed'))['seed__max'] or 0
                        StagePlayer.objects.create(
                            player=player,
                            stage=current_stage,
                            seed=max_seed + 1
                        )

                    TournamentActionLog.objects.create(
                        tournament=tournament,
                        user=request.user,
                        action_type=TournamentActionLog.ActionType.ADD_PLAYER,
                        description=f'Added player {player.get_display_name()}'
                    )

                    messages.success(
                        request, f'Player {player.get_display_name()} added successfully!')
                except IntegrityError:
                    messages.error(
                        request, 'This player is already registered for this tournament.')

        elif action == 'drop_player':
            player_id = request.POST.get('player_id')
            player = get_object_or_404(
                Player, id=player_id, tournament=tournament)
            player.status = Player.PlayerStatus.DROPPED
            player.save()

            current_stage = tournament.get_current_stage()
            current_round = current_stage.get_current_round() if current_stage else None

            if current_round:
                stage_player = current_stage.stage_players.filter(
                    player=player).first()
                if stage_player:
                    incomplete_matches = current_round.matches.filter(
                        models.Q(player_one=stage_player) | models.Q(
                            player_two=stage_player),
                        result__isnull=True
                    )

                    for match in incomplete_matches:
                        opponent = match.player_two if match.player_one == stage_player else match.player_one
                        MatchResult.objects.create(
                            match=match,
                            winner=opponent
                        )

            TournamentActionLog.objects.create(
                tournament=tournament,
                user=request.user,
                action_type=TournamentActionLog.ActionType.DROP_PLAYER,
                description=f'Dropped player {player.get_display_name()}'
            )

            messages.success(
                request, f'Player {player.get_display_name()} dropped from tournament.')

            # Return partial for htmx request
            if request.htmx:
                context = {
                    'tournament': tournament,
                    'player': player,
                }
                return render(request, 'tourney/manage-players.html#player-card', context)

        elif action == 'undrop_player':
            player_id = request.POST.get('player_id')
            player = get_object_or_404(
                Player, id=player_id, tournament=tournament)
            player.status = Player.PlayerStatus.ACTIVE
            player.save()

            TournamentActionLog.objects.create(
                tournament=tournament,
                user=request.user,
                action_type=TournamentActionLog.ActionType.UNDROP_PLAYER,
                description=f'Undropped player {player.get_display_name()}'
            )

            messages.success(
                request, f'Player {player.get_display_name()} re-added to tournament.')

            # Return partial for htmx request
            if request.htmx:
                context = {
                    'tournament': tournament,
                    'player': player,
                }
                return render(request, 'tourney/manage-players.html#player-card', context)

        return redirect_to(request, reverse('tourney-manage-players', kwargs={'tournament_id': tournament.id}))

    players = tournament.players.all().order_by('status', 'created_on')
    form = PlayerForm()

    context = {
        'tournament': tournament,
        'players': players,
        'form': form,
    }

    return render(request, 'tourney/manage-players.html', context)


@login_required
@require_POST
def report_match_result(request, tournament_id, match_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    match = get_object_or_404(
        Match, id=match_id, round__stage__tournament=tournament)

    is_admin = tournament.is_user_admin(request.user)
    is_player_in_match = (
        (match.player_one and match.player_one.player.user == request.user) or
        (match.player_two and match.player_two.player.user == request.user)
    )

    if not (is_admin or is_player_in_match):
        raise PermissionDenied

    if match.has_result() and not is_admin:
        messages.error(request, 'This match already has a result.')
        return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_id': tournament.id}))

    form = MatchResultForm(request.POST, match=match)
    if form.is_valid():
        # Check if result already exists (for admin updates)
        existing_result = getattr(match, 'result', None)
        if existing_result:
            # Update existing result
            result = form.save(commit=False)
            existing_result.winner = result.winner
            existing_result.player_one_score = result.player_one_score
            existing_result.player_two_score = result.player_two_score
            existing_result.save()
            result = existing_result
        else:
            # Create new result
            result = form.save(commit=False)
            result.match = match
            result.save()

        action_type = (TournamentActionLog.ActionType.REPORT_RESULT if not existing_result
                       else TournamentActionLog.ActionType.UPDATE_RESULT)

        winner_name = result.winner.player.get_display_name() if result.winner else 'Tie'
        TournamentActionLog.objects.create(
            tournament=tournament,
            user=request.user,
            action_type=action_type,
            description=f'Match result {"updated" if existing_result else "reported"}: {winner_name}'
        )

        messages.success(
            request, f'Match result {"updated" if existing_result else "reported"} successfully!')
    else:
        messages.error(
            request, 'Error reporting match result. Please check the form.')

    # For htmx requests, return updated match card partial
    if request.htmx:
        is_admin = tournament.is_user_admin(request.user)
        context = {
            'match': match,
            'tournament': tournament,
            'is_admin': is_admin,
        }
        return render(request, 'tourney/partials/match-card.html', context)

    return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_id': tournament.id}))


@login_required
@require_POST
@is_tournament_admin
def create_round(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)

    if not tournament.can_create_round_in_current_stage():
        messages.error(request, 'Cannot create new round at this time.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_id': tournament.id}))

    current_stage = tournament.get_current_stage()
    pairing_strategy = get_pairing_strategy(current_stage.pairing_strategy)

    with transaction.atomic():
        next_order = (current_stage.rounds.aggregate(
            models.Max('order'))['order__max'] or 0) + 1
        new_round = Round.objects.create(stage=current_stage, order=next_order)

        pairing_strategy.make_pairings_for_round(new_round)

        TournamentActionLog.objects.create(
            tournament=tournament,
            user=request.user,
            action_type=TournamentActionLog.ActionType.CREATE_ROUND,
            description=f'Created round {next_order} in stage {current_stage.name}'
        )

    messages.success(
        request, f'Round {next_order} created successfully in {current_stage.name}!')

    return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_id': tournament.id}))


@login_required
@require_POST
@is_tournament_admin
def start_next_stage(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)

    if not tournament.can_start_next_stage():
        messages.error(request, 'Cannot start next stage at this time.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_id': tournament.id}))

    try:
        with transaction.atomic():
            next_stage = tournament.advance_to_next_stage()

            TournamentActionLog.objects.create(
                tournament=tournament,
                user=request.user,
                action_type=TournamentActionLog.ActionType.ADVANCE_STAGE,
                description=f'Advanced to {next_stage.name}'
            )

        messages.success(request, f'{next_stage.name} started successfully!')
    except ValueError as e:
        messages.error(request, str(e))

    return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_id': tournament.id}))


@login_required
@require_POST
def register_for_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)

    if not tournament.is_accepting_registrations:
        messages.error(
            request, 'This tournament is not accepting registrations.')
        return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_id': tournament.id}))

    if tournament.players.filter(user=request.user).exists():
        messages.error(
            request, 'You are already registered for this tournament.')
        return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_id': tournament.id}))

    form = PlayerRegistrationForm(request.POST)
    if form.is_valid():
        try:
            player = Player.objects.create(
                user=request.user,
                tournament=tournament,
                nickname=form.cleaned_data['nickname']
            )

            current_stage = tournament.get_current_stage()
            if current_stage:
                max_seed = current_stage.stage_players.aggregate(
                    models.Max('seed'))['seed__max'] or 0
                StagePlayer.objects.create(
                    player=player,
                    stage=current_stage,
                    seed=max_seed + 1
                )

            TournamentActionLog.objects.create(
                tournament=tournament,
                user=request.user,
                action_type=TournamentActionLog.ActionType.REGISTER_PLAYER,
                description=f'Player {player.get_display_name()} registered'
            )

            messages.success(
                request, 'Successfully registered for tournament!')
        except IntegrityError:
            messages.error(
                request, 'You are already registered for this tournament.')
    else:
        messages.error(request, 'Error registering for tournament.')

    return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_id': tournament.id}))


@login_required
@require_POST
def unregister_from_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)

    try:
        player = tournament.players.get(user=request.user)
        player.delete()

        TournamentActionLog.objects.create(
            tournament=tournament,
            user=request.user,
            action_type=TournamentActionLog.ActionType.UNREGISTER_PLAYER,
            description=f'Player {request.user.username} unregistered'
        )

        messages.success(request, 'Successfully unregistered from tournament.')
    except Player.DoesNotExist:
        messages.error(request, 'You are not registered for this tournament.')

    return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_id': tournament.id}))


@login_required
@require_POST
def drop_from_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)

    try:
        player = tournament.players.get(user=request.user)
        if player.status == Player.PlayerStatus.DROPPED:
            messages.error(
                request, 'You are already dropped from this tournament.')
            return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_id': tournament.id}))

        player.status = Player.PlayerStatus.DROPPED
        player.save()

        current_stage = tournament.get_current_stage()
        current_round = current_stage.get_current_round() if current_stage else None

        if current_round:
            stage_player = current_stage.stage_players.filter(
                player=player).first()
            if stage_player:
                incomplete_matches = current_round.matches.filter(
                    models.Q(player_one=stage_player) | models.Q(
                        player_two=stage_player),
                    result__isnull=True
                )

                for match in incomplete_matches:
                    opponent = match.player_two if match.player_one == stage_player else match.player_one
                    MatchResult.objects.create(
                        match=match,
                        winner=opponent
                    )

        TournamentActionLog.objects.create(
            tournament=tournament,
            user=request.user,
            action_type=TournamentActionLog.ActionType.DROP_PLAYER,
            description=f'Player {player.get_display_name()} dropped themselves'
        )

    except Player.DoesNotExist:
        messages.error(request, 'You are not registered for this tournament.')

    if request.htmx:
        context = {
            'tournament': tournament,
            'is_player': True,
            'is_active_player': player.status == Player.PlayerStatus.ACTIVE,
            'is_dropped_player': player.status == Player.PlayerStatus.DROPPED
        }
        return render(request, 'tourney/partials/tournament-detail-registration-status.html', context)

    return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_id': tournament.id}))


@login_required
@require_POST
def undrop_from_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)

    if not tournament.is_accepting_registrations:
        messages.error(
            request, 'Cannot undrop when tournament is no longer accepting registrations.')
        return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_id': tournament.id}))

    try:
        player = tournament.players.get(user=request.user)
        if player.status == Player.PlayerStatus.ACTIVE:
            messages.error(
                request, 'You are already active in this tournament.')
            return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_id': tournament.id}))

        player.status = Player.PlayerStatus.ACTIVE
        player.save()

        TournamentActionLog.objects.create(
            tournament=tournament,
            user=request.user,
            action_type=TournamentActionLog.ActionType.UNDROP_PLAYER,
            description=f'Player {player.get_display_name()} undropped themselves'
        )

    except Player.DoesNotExist:
        messages.error(request, 'You are not registered for this tournament.')

    if request.htmx:
        context = {
            'tournament': tournament,
            'is_player': True,
            'is_active_player': player.status == Player.PlayerStatus.ACTIVE,
            'is_dropped_player': player.status == Player.PlayerStatus.DROPPED
        }
        return render(request, 'tourney/partials/tournament-detail-registration-status.html', context)

    return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_id': tournament.id}))


@login_required
@require_POST
@is_tournament_admin
def delete_latest_round(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)

    current_stage = tournament.get_current_stage()
    if not current_stage:
        messages.error(request, 'No active stage found.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_id': tournament.id}))

    latest_round = current_stage.rounds.order_by('-order').first()
    if not latest_round:
        messages.error(request, 'No rounds found to delete.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_id': tournament.id}))

    round_number = latest_round.order
    stage_name = current_stage.name

    with transaction.atomic():
        latest_round.delete()

        TournamentActionLog.objects.create(
            tournament=tournament,
            user=request.user,
            action_type=TournamentActionLog.ActionType.DELETE_ROUND,
            description=f'Deleted round {round_number} from {stage_name}'
        )

    messages.success(
        request, f'Round {round_number} deleted successfully from {stage_name}!')

    return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_id': tournament.id}))
