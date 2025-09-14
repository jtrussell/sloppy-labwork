from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tourney.models import Tournament, Player, Stage, StagePlayer, Round, Match, MatchResult, get_pairing_strategy


class Command(BaseCommand):
    help = 'Simulate a complete tournament progression to test stage advancement'

    def handle(self, *args, **options):
        # Create a fresh tournament for testing
        owner, _ = User.objects.get_or_create(
            username='sim_admin',
            defaults={'email': 'sim@example.com'}
        )
        
        tournament = Tournament.objects.create(
            name='Simulation Tournament',
            description='Testing complete tournament flow',
            owner=owner
        )
        
        # Create test players
        for i in range(8):
            user, _ = User.objects.get_or_create(
                username=f'simplayer{i+1}',
                defaults={'email': f'simplayer{i+1}@example.com'}
            )
            Player.objects.create(
                user=user,
                tournament=tournament,
                nickname=f'Sim Player {i+1}'
            )
        
        # Create stages
        tournament.create_initial_stage()
        tournament.create_playoff_stage(max_players=4)
        
        self.stdout.write(f'Created tournament: {tournament.name}')
        
        # Phase 1: Create first round in main stage
        current_stage = tournament.get_current_stage()
        self.stdout.write(f'\n=== PHASE 1: Main Stage Round 1 ===')
        self.stdout.write(f'Current stage: {current_stage.name}')
        self.stdout.write(f'Can create round: {tournament.can_create_round_in_current_stage()}')
        self.stdout.write(f'Can start next stage: {tournament.can_start_next_stage()}')
        
        # Create first round
        pairing_strategy = get_pairing_strategy(current_stage.pairing_strategy)
        round1 = Round.objects.create(stage=current_stage, order=1)
        pairing_strategy.make_pairings_for_round(round1)
        self.stdout.write(f'Created round 1 with {round1.matches.count()} matches')
        
        # Complete all matches in round 1 (simulate random results)
        import random
        for match in round1.matches.all():
            if not match.is_bye():
                winner = random.choice([match.player_one, match.player_two])
                MatchResult.objects.create(match=match, winner=winner)
                self.stdout.write(f'  {winner.player.get_display_name()} beat {"BYE" if not match.player_two else match.player_two.player.get_display_name() if match.player_two != winner else match.player_one.player.get_display_name()}')
        
        # Check status after round 1
        self.stdout.write(f'Round 1 complete: {round1.is_complete()}')
        self.stdout.write(f'Stage complete: {current_stage.is_complete()}')
        self.stdout.write(f'Can create round: {tournament.can_create_round_in_current_stage()}')
        self.stdout.write(f'Can start next stage: {tournament.can_start_next_stage()}')
        
        # Phase 2: Create second round
        self.stdout.write(f'\n=== PHASE 2: Main Stage Round 2 ===')
        round2 = Round.objects.create(stage=current_stage, order=2)
        pairing_strategy.make_pairings_for_round(round2)
        self.stdout.write(f'Created round 2 with {round2.matches.count()} matches')
        
        # Complete all matches in round 2
        for match in round2.matches.all():
            if not match.is_bye():
                winner = random.choice([match.player_one, match.player_two])
                MatchResult.objects.create(match=match, winner=winner)
        
        # Check status after round 2
        self.stdout.write(f'Round 2 complete: {round2.is_complete()}')
        self.stdout.write(f'Stage complete: {current_stage.is_complete()}')
        self.stdout.write(f'Can create round: {tournament.can_create_round_in_current_stage()}')
        self.stdout.write(f'Can start next stage: {tournament.can_start_next_stage()}')
        
        # Phase 3: Advance to playoffs
        self.stdout.write(f'\n=== PHASE 3: Advancing to Playoffs ===')
        if tournament.can_start_next_stage():
            next_stage = tournament.advance_to_next_stage()
            self.stdout.write(f'Advanced to: {next_stage.name}')
            self.stdout.write(f'Playoff players: {next_stage.stage_players.count()}')
            
            # Show seeding
            for stage_player in next_stage.stage_players.all():
                self.stdout.write(f'  Seed {stage_player.seed}: {stage_player.player.get_display_name()}')
            
            # Check new status
            current_stage = tournament.get_current_stage()
            self.stdout.write(f'New current stage: {current_stage.name}')
            self.stdout.write(f'Can create round: {tournament.can_create_round_in_current_stage()}')
            self.stdout.write(f'Can start next stage: {tournament.can_start_next_stage()}')
        
        self.stdout.write(self.style.SUCCESS('\nSimulation completed successfully!'))