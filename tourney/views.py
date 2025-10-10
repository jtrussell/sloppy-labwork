from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db import models
from django.db.models import Q
from django.db.models import F
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils.translation import gettext_lazy as _
import json

from .models import (
    Tournament, Player, TournamentAdmin, Stage, StagePlayer, Round,
    Match, MatchResult, TournamentActionLog, StandingCalculator,
    get_pairing_strategy, get_available_ranking_criteria
)
from .forms import (
    TournamentForm, PlayerForm, StageForm, MatchResultForm,
    PlayerRegistrationForm, AddMatchForm, SelectPlaygroupForm, TournamentExportForm
)
from pmc.models import Playgroup, Event, EventResult, PlaygroupEvent, RankingPointsService


def is_tournament_admin(view_func):
    def wrapper(request, tournament_code, *args, **kwargs):
        tournament = get_object_or_404(Tournament, code=tournament_code)
        if not tournament.is_user_admin(request.user):
            raise PermissionDenied
        return view_func(request, tournament_code, *args, **kwargs)
    return wrapper


def is_tournament_admin_or_player(view_func):
    def wrapper(request, tournament_code, *args, **kwargs):
        tournament = get_object_or_404(Tournament, code=tournament_code)
        if not (tournament.is_user_admin(request.user) or
                tournament.players.filter(user=request.user).exists()):
            raise PermissionDenied
        return view_func(request, tournament_code, *args, **kwargs)
    return wrapper


def can_add_match(view_func):
    def wrapper(request, tournament_code, *args, **kwargs):
        tournament = get_object_or_404(Tournament, code=tournament_code)
        current_stage = tournament.get_current_stage()

        # Allow admins always
        if tournament.is_user_admin(request.user):
            return view_func(request, tournament_code, *args, **kwargs)

        # Allow players only in self-scheduled stages
        if (current_stage and
            current_stage.get_pairing_strategy().is_self_scheduled() and
                tournament.players.filter(user=request.user).exists()):
            return view_func(request, tournament_code, *args, **kwargs)

        raise PermissionDenied
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
                    main_max_players=form.cleaned_data['main_max_players'],
                    main_allow_ties=form.cleaned_data['main_allow_ties'],
                    main_score_reporting=form.cleaned_data['main_score_reporting']
                )

                # Set ranking criteria for main stage
                ranking_criteria = form.get_ranking_criteria_from_post(
                    request.POST)
                main_stage.set_ranking_criteria(ranking_criteria)

                # Create playoff stage if enabled
                if form.cleaned_data['enable_playoffs']:
                    tournament.create_playoff_stage(
                        max_players=form.cleaned_data['playoff_max_players'],
                        playoff_score_reporting=form.cleaned_data['playoff_score_reporting']
                    )

                TournamentActionLog.objects.create(
                    tournament=tournament,
                    user=request.user,
                    action_type=TournamentActionLog.ActionType.CREATE_TOURNAMENT,
                    description=f'Tournament "{tournament.name}" created'
                )

            messages.success(
                request, f'Tournament "{tournament.name}" created successfully!')
            return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))
    else:
        form = TournamentForm(is_edit_mode=False)

    available_criteria = get_available_ranking_criteria()
    return render(request, 'tourney/tournament-form.html', {
        'form': form,
        'available_criteria': available_criteria
    })


@login_required
@is_tournament_admin
def edit_tournament(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)

    if request.method == 'POST':
        form = TournamentForm(
            request.POST, instance=tournament, is_edit_mode=True)
        if form.is_valid():
            with transaction.atomic():
                form.save()

                # Update main stage
                main_stage = tournament.stages.filter(order=1).first()
                if main_stage:
                    main_stage.pairing_strategy = form.cleaned_data['main_pairing_strategy']
                    main_stage.max_players = form.cleaned_data['main_max_players']
                    main_stage.are_ties_allowed = form.cleaned_data['main_allow_ties']
                    main_stage.report_full_scores = form.cleaned_data['main_score_reporting']

                    # Update ranking criteria for main stage
                    ranking_criteria = form.get_ranking_criteria_from_post(
                        request.POST)
                    main_stage.set_ranking_criteria(ranking_criteria)

                    main_stage.save()
                else:
                    # Create main stage if it doesn't exist
                    main_stage = tournament.create_initial_stage(
                        main_pairing_strategy=form.cleaned_data['main_pairing_strategy'],
                        main_max_players=form.cleaned_data['main_max_players'],
                        main_allow_ties=form.cleaned_data['main_allow_ties'],
                        main_score_reporting=form.cleaned_data['main_score_reporting']
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
                        playoff_stage.report_full_scores = form.cleaned_data['playoff_score_reporting']
                        playoff_stage.save()
                    else:
                        tournament.create_playoff_stage(
                            max_players=form.cleaned_data['playoff_max_players'],
                            playoff_score_reporting=form.cleaned_data['playoff_score_reporting']
                        )
                elif playoff_stage:
                    # Remove playoff stage if it exists but is disabled
                    playoff_stage.delete()

            messages.success(request, 'Tournament updated successfully!')
            return redirect_to(request, reverse('tourney-edit-tournament', kwargs={'tournament_code': tournament.code}))
    else:
        form = TournamentForm(instance=tournament, is_edit_mode=True)

    # Get available criteria for the template
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
    return render(request, 'tourney/tournament-form.html', context)


def get_tournament_base_context(request, tournament):
    current_stage = tournament.get_current_stage()
    current_round = current_stage.get_current_round() if current_stage else None

    is_admin = False
    player = None
    is_player = False
    is_active_player = False
    is_dropped_player = False

    if request.user.is_authenticated:
        is_admin = tournament.is_user_admin(request.user)
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
    can_start_current_stage = False
    next_stage = None
    if is_admin:
        can_create_round = tournament.can_create_round_in_current_stage()
        can_start_next_stage = tournament.can_start_next_stage()
        next_stage = tournament.get_next_stage()

        # Check if current stage needs seeding confirmation (no rounds yet)
        if current_stage and not current_stage.rounds.exists():
            can_start_current_stage = True
            can_create_round = False  # Override - we want seeding confirmation instead

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
        'can_start_current_stage': can_start_current_stage,
        'next_stage': next_stage,
        'current_stage': current_stage,
        'current_round': current_round,
        'pending_matches': pending_matches,
        'user': request.user,
    }


def tournament_detail_matches(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    context = get_tournament_base_context(request, tournament)
    context['current_tab'] = 'matches'

    # Get all stages ordered by creation (most recent first)
    stages = tournament.stages.prefetch_related(
        'rounds__matches__result',
        'rounds__matches__player_one__player',
        'rounds__matches__player_two__player'
    ).order_by('-created_on')

    # Build grouped matches structure
    grouped_matches = []
    current_stage = context['current_stage']
    latest_round = None
    unmatched_players = []

    for stage in stages:
        stage_rounds = []
        for round_obj in stage.rounds.order_by('-order'):
            if round_obj.matches.exists():
                stage_rounds.append({
                    'round': round_obj,
                    'matches': round_obj.matches.all()
                })
                # Track the most recent round for unmatched players logic
                if not latest_round and stage == current_stage:
                    latest_round = round_obj

        if stage_rounds:
            grouped_matches.append({
                'stage': stage,
                'rounds': stage_rounds
            })

    # Calculate available players for the current stage
    if current_stage:
        stage_players = current_stage.stage_players.filter(
            player__status=Player.PlayerStatus.ACTIVE)

        # For self-scheduled stages, show all active players
        # For other stages, only show unmatched players from the latest round
        pairing_strategy = current_stage.get_pairing_strategy()
        if pairing_strategy.is_self_scheduled():
            unmatched_players = stage_players
        elif latest_round:
            matched_player_ids = set()
            for match in latest_round.matches.all():
                if match.player_one:
                    matched_player_ids.add(match.player_one.id)
                if match.player_two:
                    matched_player_ids.add(match.player_two.id)
            unmatched_players = stage_players.exclude(
                id__in=matched_player_ids)
        else:
            # No rounds yet, all players are available
            unmatched_players = stage_players

    # Check if current user can add matches
    can_add_match = False
    can_report_result = False
    show_unmatched_players = True
    if current_stage:
        pairing_strategy = current_stage.get_pairing_strategy()
        is_self_scheduled = pairing_strategy.is_self_scheduled()
        is_elimination_style = pairing_strategy.is_elimination_style()

        if request.user.is_authenticated:
            user_is_admin = tournament.is_user_admin(request.user)
            user_is_player = tournament.players.filter(
                user=request.user).exists()
            can_report_result = is_self_scheduled and user_is_player
            can_add_match = user_is_admin or can_report_result

        show_unmatched_players = not (
            is_elimination_style or is_self_scheduled)

    unmatched_players_json = json.dumps([{
        'id': sp.id,
        'name': sp.player.get_display_name(),
        'userId': sp.player.user.id if sp.player.user else None
    } for sp in unmatched_players])

    context.update({
        'grouped_matches': grouped_matches,
        'latest_round': latest_round,
        'unmatched_players': unmatched_players,
        'unmatched_players_json': unmatched_players_json,
        'can_add_match': can_add_match,
        'can_report_result': can_report_result,
        'show_unmatched_players': show_unmatched_players,
        'selected_stage': current_stage,
    })

    if request.htmx:
        return render(request, 'tourney/partials/tournament-detail-matches-content.html', context)
    return render(request, 'tourney/tournament-detail-matches.html', context)


def tournament_detail_standings(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    context = get_tournament_base_context(request, tournament)
    context['current_tab'] = 'standings'

    standings = []
    enabled_criteria = []
    if context['current_stage']:
        standings = StandingCalculator.get_tournament_standings(tournament)
        enabled_criteria = context['current_stage'].get_enabled_ranking_criteria_objects(
        )

    context['standings'] = standings
    context['enabled_criteria'] = enabled_criteria

    if request.htmx:
        return render(request, 'tourney/partials/tournament-detail-standings-content.html', context)
    return render(request, 'tourney/tournament-detail-standings.html', context)


@login_required
@is_tournament_admin
def tournament_detail_admin(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    context = get_tournament_base_context(request, tournament)
    context['current_tab'] = 'admin'

    logs = tournament.action_logs.select_related('user').order_by(
        '-created_on')[:100]
    context['tournament_logs'] = logs

    tournament_logs_json = json.dumps([{
        'date': log.created_on.strftime('%b %d, %Y %I:%M %p'),
        'user': log.user.username if log.user else 'System',
        'action': log.get_action_type_display(),
        'description': log.description or ''
    } for log in logs])
    context['tournament_logs_json'] = tournament_logs_json

    user_has_playgroup_staff_access = Playgroup.objects.filter(
        members__user=request.user,
        members__is_staff=True
    ).exists()
    context['user_has_playgroup_staff_access'] = user_has_playgroup_staff_access

    if request.htmx:
        return render(request, 'tourney/partials/tournament-detail-admin-content.html', context)
    return render(request, 'tourney/tournament-detail-admin.html', context)


@login_required
@is_tournament_admin
def manage_players(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)

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
                return render(request, 'tourney/manage-players.html#player-item', context)

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
                return render(request, 'tourney/manage-players.html#player-item', context)

        return redirect_to(request, reverse('tourney-manage-players', kwargs={'tournament_code': tournament.code}))

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
def report_match_result(request, tournament_code, match_id):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    match = get_object_or_404(
        Match, id=match_id, round__stage__tournament=tournament)

    is_admin = tournament.is_user_admin(request.user)
    is_player_in_match = (
        (match.player_one and match.player_one.player.user == request.user) or
        (match.player_two and match.player_two.player.user == request.user)
    )

    if not (is_admin or is_player_in_match):
        raise PermissionDenied

    # Check if tournament is closed for non-admin users
    if tournament.is_closed and not is_admin:
        messages.error(
            request, 'This tournament is closed. Match results can no longer be submitted by players.')
        return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))

    if match.has_result() and not is_admin:
        messages.error(request, 'This match already has a result.')
        return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))

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

    return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))


@login_required
@require_POST
@is_tournament_admin
def create_round(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)

    if not tournament.can_create_round_in_current_stage():
        messages.error(request, 'Cannot create new round at this time.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

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

    return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))


@login_required
@require_POST
@is_tournament_admin
def prepare_stage_seeding(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)

    if not tournament.can_start_next_stage():
        messages.error(request, 'Cannot start next stage at this time.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    next_stage = tournament.get_next_stage()
    pairing_strategy = get_pairing_strategy(next_stage.pairing_strategy)

    # Check if seeding is required for this pairing strategy
    if not pairing_strategy.is_seeding_required():
        # Skip seeding confirmation and start the stage directly
        try:
            with transaction.atomic():
                tournament.advance_to_next_stage()

                TournamentActionLog.objects.create(
                    tournament=tournament,
                    user=request.user,
                    action_type=TournamentActionLog.ActionType.ADVANCE_STAGE,
                    description=f'Started {next_stage.name} (no seeding required)'
                )

            messages.success(
                request, f'{next_stage.name} started successfully!')
            return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))
        except ValueError as e:
            messages.error(request, str(e))
            return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    # Seeding is required, proceed with confirmation workflow
    try:
        with transaction.atomic():
            next_stage = tournament.prepare_next_stage_seeding()

            TournamentActionLog.objects.create(
                tournament=tournament,
                user=request.user,
                action_type=TournamentActionLog.ActionType.ADVANCE_STAGE,
                description=f'Prepared seeding for {next_stage.name}'
            )

        return redirect_to(request, reverse('tourney-confirm-seeding', kwargs={'tournament_code': tournament.code}))
    except ValueError as e:
        messages.error(request, str(e))
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))


@login_required
@require_POST
@is_tournament_admin
def prepare_current_stage_seeding(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    current_stage = tournament.get_current_stage()

    if not current_stage:
        messages.error(request, 'No current stage found.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    if current_stage.rounds.exists():
        messages.error(request, 'Current stage already has rounds.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    pairing_strategy = get_pairing_strategy(current_stage.pairing_strategy)

    # Ensure StagePlayer records exist
    if not current_stage.stage_players.exists():
        # Create stage players if they don't exist
        for i, player in enumerate(tournament.get_active_players()):
            StagePlayer.objects.create(
                player=player,
                stage=current_stage,
                seed=i + 1
            )

    # Check if seeding is required for this pairing strategy
    if not pairing_strategy.is_seeding_required():
        # Skip seeding confirmation and start the stage directly
        try:
            with transaction.atomic():
                # Create first round in current stage
                new_round = Round.objects.create(stage=current_stage, order=1)
                pairing_strategy.make_pairings_for_round(new_round)

                TournamentActionLog.objects.create(
                    tournament=tournament,
                    user=request.user,
                    action_type=TournamentActionLog.ActionType.ADVANCE_STAGE,
                    description=f'Started {current_stage.name} (no seeding required)'
                )

            messages.success(
                request, f'{current_stage.name} started successfully!')
            return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))
        except ValueError as e:
            messages.error(request, str(e))
            return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    # Seeding is required, proceed with confirmation workflow
    try:
        with transaction.atomic():
            TournamentActionLog.objects.create(
                tournament=tournament,
                user=request.user,
                action_type=TournamentActionLog.ActionType.ADVANCE_STAGE,
                description=f'Prepared seeding for {current_stage.name}'
            )

        return redirect_to(request, reverse('tourney-confirm-seeding', kwargs={'tournament_code': tournament.code}))
    except ValueError as e:
        messages.error(request, str(e))
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))


@login_required
@is_tournament_admin
def confirm_seeding(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    current_stage = tournament.get_current_stage()
    next_stage = tournament.get_next_stage()

    # Determine which stage we're confirming seeding for
    if current_stage and not current_stage.rounds.exists():
        # We're confirming seeding for the current stage (first time starting it)
        target_stage = current_stage
        stage_name = current_stage.name
    elif next_stage and tournament.can_modify_next_stage_seeding():
        # We're confirming seeding for the next stage
        target_stage = next_stage
        stage_name = next_stage.name
    else:
        messages.error(request, 'No stage available for seeding confirmation.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    stage_players = target_stage.stage_players.order_by('seed')

    # Calculate advancement information
    total_players = stage_players.count()
    max_players = target_stage.max_players
    players_advancing = min(
        max_players, total_players) if max_players else total_players
    all_players_advance = not max_players or max_players >= total_players

    context = {
        'tournament': tournament,
        'next_stage': target_stage,  # Keep same template variable name for compatibility
        'stage_players': stage_players,
        'is_current_stage': target_stage == current_stage,
        'total_players': total_players,
        'players_advancing': players_advancing,
        'all_players_advance': all_players_advance,
    }

    return render(request, 'tourney/confirm-seeding.html', context)


@login_required
@require_POST
@is_tournament_admin
def update_seeding_order(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    current_stage = tournament.get_current_stage()
    next_stage = tournament.get_next_stage()

    # Determine which stage we're updating seeding for
    if current_stage and not current_stage.rounds.exists():
        target_stage = current_stage
    elif next_stage and tournament.can_modify_next_stage_seeding():
        target_stage = next_stage
    else:
        return HttpResponse(status=400)

    try:
        player_ids = request.POST.get('player_order', '').split(',')
        player_ids = [int(pid) for pid in player_ids if pid.strip()]

        with transaction.atomic():
            # Calculate safe increment to avoid constraint conflicts
            max_seed = target_stage.stage_players.aggregate(models.Max('seed'))[
                'seed__max'] or 0
            safe_increment = max(100, max_seed + 100)

            # First, increment all seeds by safe amount to avoid conflicts
            target_stage.stage_players.update(seed=F('seed') + safe_increment)

            # Then update to final values in the correct order
            for i, player_id in enumerate(player_ids):
                StagePlayer.objects.filter(
                    id=player_id,
                    stage=target_stage
                ).update(seed=i + 1)

        stage_players = target_stage.stage_players.order_by('seed')
        context = {
            'tournament': tournament,
            'next_stage': target_stage,  # Keep same template variable name for compatibility
            'stage_players': stage_players,
        }

        return render(request, 'tourney/partials/seeding-list.html', context)
    except (ValueError, StagePlayer.DoesNotExist):
        return HttpResponse(status=400)


@login_required
@require_POST
@is_tournament_admin
def randomize_seeding(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    current_stage = tournament.get_current_stage()
    next_stage = tournament.get_next_stage()

    # Determine which stage we're randomizing seeding for
    if current_stage and not current_stage.rounds.exists():
        target_stage = current_stage
    elif next_stage and tournament.can_modify_next_stage_seeding():
        target_stage = next_stage
    else:
        return HttpResponse(status=400)

    import random

    with transaction.atomic():
        stage_players = list(target_stage.stage_players.all())
        random.shuffle(stage_players)

        # Calculate safe increment to avoid constraint conflicts
        max_seed = target_stage.stage_players.aggregate(models.Max('seed'))[
            'seed__max'] or 0
        safe_increment = max(100, max_seed + 100)

        # First, increment all seeds by safe amount to avoid conflicts
        target_stage.stage_players.update(seed=F('seed') + safe_increment)

        # Then set to final randomized values
        for i, stage_player in enumerate(stage_players):
            stage_player.seed = i + 1
            stage_player.save()

    stage_players = target_stage.stage_players.order_by('seed')
    context = {
        'tournament': tournament,
        'next_stage': target_stage,  # Keep same template variable name for compatibility
        'stage_players': stage_players,
    }

    return render(request, 'tourney/partials/seeding-list.html', context)


@login_required
@require_POST
@is_tournament_admin
def start_next_stage(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    current_stage = tournament.get_current_stage()
    next_stage = tournament.get_next_stage()

    # Determine which stage we're starting
    if current_stage and not current_stage.rounds.exists():
        # Starting the current stage for the first time
        target_stage = current_stage
        stage_name = current_stage.name

        try:
            with transaction.atomic():
                # Create first round in current stage using existing StagePlayer records
                pairing_strategy = get_pairing_strategy(
                    current_stage.pairing_strategy)
                new_round = Round.objects.create(stage=current_stage, order=1)
                pairing_strategy.make_pairings_for_round(new_round)

                TournamentActionLog.objects.create(
                    tournament=tournament,
                    user=request.user,
                    action_type=TournamentActionLog.ActionType.ADVANCE_STAGE,
                    description=f'Started {stage_name} with confirmed seeding'
                )

            messages.success(request, f'{stage_name} started successfully!')
        except ValueError as e:
            messages.error(request, str(e))

    elif next_stage and tournament.can_modify_next_stage_seeding():
        # Starting the next stage (existing logic)
        try:
            with transaction.atomic():
                tournament.advance_to_next_stage()

                TournamentActionLog.objects.create(
                    tournament=tournament,
                    user=request.user,
                    action_type=TournamentActionLog.ActionType.ADVANCE_STAGE,
                    description=f'Started {next_stage.name} with confirmed seeding'
                )

            messages.success(
                request, f'{next_stage.name} started successfully!')
        except ValueError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, 'Cannot start stage at this time.')

    return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))


@login_required
@require_POST
def register_for_tournament(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)

    if tournament.is_closed:
        messages.error(
            request, 'This tournament is closed. No further registrations are allowed.')
        return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))

    if not tournament.is_accepting_registrations:
        messages.error(
            request, 'This tournament is not accepting registrations.')
        return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))

    if tournament.players.filter(user=request.user).exists():
        messages.error(
            request, 'You are already registered for this tournament.')
        return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))

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

    return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))


@login_required
@require_POST
def unregister_from_tournament(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)

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

    return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))


@login_required
@require_POST
def drop_from_tournament(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)

    if tournament.is_closed:
        messages.error(
            request, 'This tournament is closed. Players can no longer drop or make changes.')
        return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))

    try:
        player = tournament.players.get(user=request.user)
        if player.status == Player.PlayerStatus.DROPPED:
            messages.error(
                request, 'You are already dropped from this tournament.')
            return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))

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

    return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))


@login_required
@require_POST
def undrop_from_tournament(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)

    if tournament.is_closed:
        messages.error(
            request, 'This tournament is closed. Players can no longer rejoin or make changes.')
        return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))

    if not tournament.is_accepting_registrations:
        messages.error(
            request, 'Cannot undrop when tournament is no longer accepting registrations.')
        return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))

    try:
        player = tournament.players.get(user=request.user)
        if player.status == Player.PlayerStatus.ACTIVE:
            messages.error(
                request, 'You are already active in this tournament.')
            return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))

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

    return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))


@login_required
@require_POST
@is_tournament_admin
def delete_latest_round(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)

    current_stage = tournament.get_current_stage()
    if not current_stage:
        messages.error(request, 'No active stage found.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    latest_round = current_stage.rounds.order_by('-order').first()
    if not latest_round:
        messages.error(request, 'No rounds found to delete.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

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

    return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))


@login_required
@require_POST
@is_tournament_admin
def delete_match(request, tournament_code, match_id):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    match = get_object_or_404(
        Match, id=match_id, round__stage__tournament=tournament)

    player_one_name = match.player_one.player.get_display_name(
    ) if match.player_one else "Unknown"
    player_two_name = match.player_two.player.get_display_name(
    ) if match.player_two else "Unknown"
    round_info = f"Round {match.round.order} in {match.round.stage.name}"

    with transaction.atomic():
        match.delete()

        TournamentActionLog.objects.create(
            tournament=tournament,
            user=request.user,
            action_type=TournamentActionLog.ActionType.DELETE_ROUND,
            description=f'Deleted match: {player_one_name} vs {player_two_name} from {round_info}'
        )

    messages.success(
        request, f'Match between {player_one_name} and {player_two_name} deleted successfully!')

    return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))


@login_required
@require_POST
@is_tournament_admin
def reset_match(request, tournament_code, match_id):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    match = get_object_or_404(
        Match, id=match_id, round__stage__tournament=tournament)

    if not match.has_result():
        messages.error(request, 'This match has no result to reset.')
        return redirect_to(request, reverse('tourney-detail-standings', kwargs={'tournament_code': tournament.code}))

    player_one_name = match.player_one.player.get_display_name(
    ) if match.player_one else "Unknown"
    player_two_name = match.player_two.player.get_display_name(
    ) if match.player_two else "Unknown"
    round_info = f"Round {match.round.order} in {match.round.stage.name}"

    with transaction.atomic():
        match.result.delete()

        TournamentActionLog.objects.create(
            tournament=tournament,
            user=request.user,
            action_type=TournamentActionLog.ActionType.UPDATE_RESULT,
            description=f'Reset match result: {player_one_name} vs {player_two_name} from {round_info}'
        )

    messages.success(
        request, f'Match result between {player_one_name} and {player_two_name} has been reset successfully!')

    return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))


@login_required
@require_POST
@can_add_match
def add_match(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    current_stage = tournament.get_current_stage()

    if not current_stage:
        messages.error(request, 'No active stage found.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    current_round = current_stage.get_current_round()
    if not current_round:
        messages.error(
            request, 'No active round found. Please create a round first.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    # Get available players for this round
    stage_players = current_stage.stage_players.filter(
        player__status=Player.PlayerStatus.ACTIVE)

    # For self-scheduled stages, show all active players
    # For other stages, only show unmatched players
    pairing_strategy = current_stage.get_pairing_strategy()
    if pairing_strategy.is_self_scheduled():
        available_players = stage_players
    else:
        matched_player_ids = set()
        for match in current_round.matches.all():
            if match.player_one:
                matched_player_ids.add(match.player_one.id)
            if match.player_two:
                matched_player_ids.add(match.player_two.id)
        available_players = stage_players.exclude(id__in=matched_player_ids)

    # For non-admin players, restrict to only include themselves
    is_admin = tournament.is_user_admin(request.user)
    if not is_admin:
        user_stage_player = available_players.filter(
            player__user=request.user).first()
        if not user_stage_player:
            messages.error(
                request, 'You are not available to create a match in this round.')
            return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    if available_players.count() < 1:
        error_message = ('No active players available to create a match.' if pairing_strategy.is_self_scheduled()
                         else 'No unmatched players available to create a match.')
        messages.error(request, error_message)
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    form = AddMatchForm(request.POST, available_players=available_players)
    if form.is_valid():
        player_one, player_two = form.get_selected_players()

        # For non-admin players, ensure they are one of the participants
        # and they cannot create bye matches for themselves
        if not is_admin:
            user_stage_player = current_stage.stage_players.filter(
                player__user=request.user).first()

            # Check if user is one of the participants
            participants = [p for p in [
                player_one, player_two] if p is not None]
            if user_stage_player not in participants:
                messages.error(
                    request, 'You can only create matches where you are a participant.')
                return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

            # Prevent non-admin players from creating bye matches for themselves
            if player_two is None and player_one == user_stage_player:
                messages.error(
                    request, 'You cannot award yourself a bye. Only admins can create bye matches.')
                return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

        with transaction.atomic():
            match = Match.objects.create(
                round=current_round,
                player_one=player_one,
                player_two=player_two
            )

            # For bye matches, automatically create a match result awarding the win to player_one
            if player_two is None:
                MatchResult.objects.create(
                    match=match,
                    winner=player_one,
                    player_one_score=None,
                    player_two_score=None
                )

            # Create appropriate log message based on match type
            if player_two:
                match_description = f'Added match: {player_one.player.get_display_name()} vs {player_two.player.get_display_name()} in {current_round.stage.name} Round {current_round.order}'
            else:
                match_description = f'Added bye match: {player_one.player.get_display_name()} received a bye in {current_round.stage.name} Round {current_round.order}'

            TournamentActionLog.objects.create(
                tournament=tournament,
                user=request.user,
                action_type=TournamentActionLog.ActionType.CREATE_ROUND,
                description=match_description
            )

        # Create appropriate success message based on match type
        if player_two:
            messages.success(
                request, f'Match between {player_one.player.get_display_name()} and {player_two.player.get_display_name()} created successfully!')
        else:
            messages.success(
                request, f'Bye match for {player_one.player.get_display_name()} created successfully!')
    else:
        if form.errors:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
        else:
            messages.error(
                request, 'Error creating match. Please check your selections.')

    return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))


@login_required
@require_POST
@can_add_match
def player_add_match_result(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)

    # Check if tournament is closed
    if tournament.is_closed:
        messages.error(
            request, 'This tournament is closed. Match results can no longer be submitted by players.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    current_stage = tournament.get_current_stage()

    if not current_stage:
        messages.error(request, 'No active stage found.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    current_round = current_stage.get_current_round()
    if not current_round:
        messages.error(
            request, 'No active round found. Please create a round first.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    # Get current user's stage player
    user_stage_player = current_stage.stage_players.filter(
        player__user=request.user).first()
    if not user_stage_player:
        messages.error(request, 'You are not a participant in this stage.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    # Get opponent stage player
    opponent_id = request.POST.get('opponent')
    if not opponent_id:
        messages.error(request, 'Please select an opponent.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    try:
        opponent_stage_player = current_stage.stage_players.get(id=opponent_id)
    except StagePlayer.DoesNotExist:
        messages.error(request, 'Invalid opponent selected.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    # Check if these players already have a match in this round
    existing_match = current_round.matches.filter(
        Q(player_one=user_stage_player, player_two=opponent_stage_player) |
        Q(player_one=opponent_stage_player, player_two=user_stage_player)
    ).first()

    if existing_match:
        messages.error(
            request, 'You already have a match against this opponent in this round.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    # Get winner information
    winner_choice = request.POST.get('winner')
    if not winner_choice:
        messages.error(request, 'Please select a winner.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    # Determine winner based on choice
    if winner_choice == 'me':
        winner = user_stage_player
    elif winner_choice == 'them':
        winner = opponent_stage_player
    elif winner_choice == 'tie':
        if not current_stage.are_ties_allowed:
            messages.error(request, 'Ties are not allowed in this stage.')
            return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))
        winner = None
    else:
        messages.error(request, 'Invalid winner selection.')
        return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

    # Get scores if provided
    my_score = request.POST.get('my_score', '').strip()
    their_score = request.POST.get('their_score', '').strip()

    player_one_score = None
    player_two_score = None

    if current_stage.report_full_scores > 0:
        # Score reporting is enabled
        if current_stage.report_full_scores == 2:
            # Required
            if not my_score or not their_score:
                messages.error(request, 'Scores are required for this stage.')
                return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))

        if my_score:
            try:
                my_score = int(my_score)
                if my_score < 0:
                    raise ValueError()
            except (ValueError, TypeError):
                messages.error(request, 'Invalid score entered.')
                return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))
        else:
            my_score = None

        if their_score:
            try:
                their_score = int(their_score)
                if their_score < 0:
                    raise ValueError()
            except (ValueError, TypeError):
                messages.error(request, 'Invalid score entered.')
                return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))
        else:
            their_score = None

        # Assign scores based on player positions (user is always player_one in this setup)
        player_one_score = my_score
        player_two_score = their_score

    with transaction.atomic():
        # Create the match
        match = Match.objects.create(
            round=current_round,
            player_one=user_stage_player,
            player_two=opponent_stage_player
        )

        # Create the match result
        MatchResult.objects.create(
            match=match,
            winner=winner,
            player_one_score=player_one_score,
            player_two_score=player_two_score
        )

        # Log the action
        TournamentActionLog.objects.create(
            tournament=tournament,
            user=request.user,
            action_type=TournamentActionLog.ActionType.CREATE_ROUND,
            description=f'Player reported match result: {user_stage_player.player.get_display_name()} vs {opponent_stage_player.player.get_display_name()} in {current_round.stage.name} Round {current_round.order}'
        )

    winner_name = winner.player.get_display_name() if winner else "Tie"
    messages.success(
        request, f'Match result submitted successfully! Winner: {winner_name}')

    return redirect_to(request, reverse('tourney-detail-matches', kwargs={'tournament_code': tournament.code}))


@login_required
@is_tournament_admin
def copy_tournament(request, tournament_code):
    """Copy an existing tournament's settings to create a new tournament."""
    source_tournament = get_object_or_404(Tournament, code=tournament_code)

    if request.method == 'POST':
        # Handle the form submission for creating the new tournament
        form = TournamentForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                tournament = form.save(commit=False)
                tournament.owner = request.user
                tournament.save()

                # Create main stage
                main_stage = tournament.create_initial_stage(
                    main_pairing_strategy=form.cleaned_data['main_pairing_strategy'],
                    main_max_players=form.cleaned_data['main_max_players'],
                    main_allow_ties=form.cleaned_data['main_allow_ties'],
                    main_score_reporting=form.cleaned_data['main_score_reporting']
                )

                # Set ranking criteria for main stage from source tournament
                source_main_stage = source_tournament.stages.filter(
                    order=1).first()
                if source_main_stage:
                    # Get ranking criteria with order information
                    criteria_qs = source_main_stage.stage_ranking_criteria.all().order_by('order')
                    source_criteria = [
                        {'key': c.criterion_key, 'enabled': True, 'order': c.order}
                        for c in criteria_qs
                    ]
                    main_stage.set_ranking_criteria(source_criteria)

                # Create playoff stage if enabled
                if form.cleaned_data['enable_playoffs']:
                    playoff_stage = tournament.create_playoff_stage(
                        max_players=form.cleaned_data['playoff_max_players'],
                        playoff_score_reporting=form.cleaned_data['playoff_score_reporting']
                    )

                    # Set ranking criteria for playoff stage from source tournament
                    source_playoff_stage = source_tournament.stages.filter(
                        order=2).first()
                    if source_playoff_stage:
                        # Get ranking criteria with order information
                        criteria_qs = source_playoff_stage.stage_ranking_criteria.all().order_by('order')
                        source_playoff_criteria = [
                            {'key': c.criterion_key,
                                'enabled': True, 'order': c.order}
                            for c in criteria_qs
                        ]
                        playoff_stage.set_ranking_criteria(
                            source_playoff_criteria)

                TournamentActionLog.objects.create(
                    tournament=tournament,
                    user=request.user,
                    action_type=TournamentActionLog.ActionType.CREATE_TOURNAMENT,
                    description=f'Tournament "{tournament.name}" created by copying from "{source_tournament.name}"'
                )

            messages.success(
                request, f'Tournament "{tournament.name}" created successfully from copy!')
            return redirect_to(request, reverse('tourney-detail-home', kwargs={'tournament_code': tournament.code}))
    else:
        # Pre-populate form with source tournament data
        initial_data = {
            'name': f'Copy of {source_tournament.name}',
            'description': source_tournament.description,
            'is_accepting_registrations': source_tournament.is_accepting_registrations,
        }

        # Get main stage data
        source_main_stage = source_tournament.stages.filter(order=1).first()
        if source_main_stage:
            initial_data.update({
                'main_pairing_strategy': source_main_stage.pairing_strategy,
                'main_max_players': source_main_stage.max_players,
                'main_allow_ties': source_main_stage.are_ties_allowed,
                'main_score_reporting': source_main_stage.report_full_scores,
            })

        # Get playoff stage data
        source_playoff_stage = source_tournament.stages.filter(order=2).first()
        if source_playoff_stage:
            initial_data.update({
                'enable_playoffs': True,
                'playoff_max_players': source_playoff_stage.max_players,
                'playoff_score_reporting': source_playoff_stage.report_full_scores,
            })
        else:
            initial_data['enable_playoffs'] = False

        form = TournamentForm(initial=initial_data, is_edit_mode=False)

    # Prepare ranking criteria data for JavaScript
    ranking_criteria_data = []
    source_main_stage = source_tournament.stages.filter(order=1).first()
    if source_main_stage:
        # Get ranking criteria with order information
        criteria_qs = source_main_stage.stage_ranking_criteria.all().order_by('order')
        available_keys = [c.get_key()
                          for c in get_available_ranking_criteria()]

        # Add enabled criteria with their actual order
        for criterion in criteria_qs:
            ranking_criteria_data.append({
                'key': criterion.criterion_key,
                'enabled': True,
                'order': criterion.order
            })

        # Add disabled criteria
        enabled_keys = [c.criterion_key for c in criteria_qs]
        for key in available_keys:
            if key not in enabled_keys:
                ranking_criteria_data.append({
                    'key': key,
                    'enabled': False,
                    'order': 999  # High number for disabled criteria
                })

    context = {
        'form': form,
        'source_tournament': source_tournament,
        'tournament': source_tournament,  # For JavaScript compatibility
        'current_criteria_json': json.dumps(ranking_criteria_data),
        'available_criteria': get_available_ranking_criteria(),
    }

    return render(request, 'tourney/tournament-form.html', context)


@login_required
@require_POST
@is_tournament_admin
def delete_tournament(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    tournament_name = tournament.name
    tournament.delete()
    messages.success(
        request, f'Tournament "{tournament_name}" has been successfully deleted.')
    return redirect_to(request, reverse('tourney-my-tournaments'))


@login_required
@is_tournament_admin
def export_to_keychain_select_playgroup(request, tournament_code):
    tournament = get_object_or_404(Tournament, code=tournament_code)

    user_playgroups = Playgroup.objects.filter(
        members__user=request.user,
        members__is_staff=True
    ).distinct()

    if not user_playgroups.exists():
        messages.error(request, 'You must be staff for at least one playgroup to export events.')
        return redirect_to(request, reverse('tourney-tournament-detail-admin', args=[tournament_code]))

    if request.method == 'POST':
        form = SelectPlaygroupForm(request.POST, user=request.user)
        if form.is_valid():
            playgroup = form.cleaned_data['playgroup']
            return redirect_to(request, reverse('tourney-export-to-keychain-form',
                                              args=[tournament_code, playgroup.slug]))
    else:
        form = SelectPlaygroupForm(user=request.user)

    context = get_tournament_base_context(request, tournament)
    context['form'] = form
    context['current_tab'] = 'admin'

    return render(request, 'tourney/export-select-playgroup.html', context)


@login_required
@is_tournament_admin
def export_to_keychain_form(request, tournament_code, playgroup_slug):
    tournament = get_object_or_404(Tournament, code=tournament_code)
    playgroup = get_object_or_404(Playgroup, slug=playgroup_slug)

    if not playgroup.members.filter(user=request.user, is_staff=True).exists():
        raise PermissionDenied

    if request.method == 'POST':
        form = TournamentExportForm(request.POST, tournament=tournament)
        if form.is_valid():
            with transaction.atomic():
                is_casual = form.cleaned_data['is_casual'] == 'True'

                event = Event.objects.create(
                    name=form.cleaned_data['name'],
                    start_date=form.cleaned_data['start_date'],
                    is_casual=is_casual,
                    format=form.cleaned_data.get('format')
                )

                PlaygroupEvent.objects.create(
                    playgroup=playgroup,
                    event=event
                )

                standings = StandingCalculator.get_tournament_standings(tournament)

                for standing in standings:
                    player = standing['player']
                    if player.user:
                        event_result = EventResult.objects.create(
                            event=event,
                            user=player.user,
                            finishing_position=standing['tournament_rank'],
                            num_wins=standing.get('wins'),
                            num_losses=standing.get('losses')
                        )

                event.player_count = len([s for s in standings if s['player'].user])
                event.save()

                if not is_casual:
                    RankingPointsService.assign_points_for_event(event)

                tournament.pmc_event = event
                tournament.save()

                messages.success(request, f'Event "{event.name}" has been successfully created in KeyChain!')
                return redirect_to(request, f'/pmc/events/{event.id}/')
    else:
        form = TournamentExportForm(tournament=tournament)

    context = get_tournament_base_context(request, tournament)
    context['form'] = form
    context['playgroup'] = playgroup
    context['current_tab'] = 'admin'
    context['tournament_standings'] = StandingCalculator.get_tournament_standings(tournament)

    return render(request, 'tourney/export-form.html', context)
