from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tourney.models import Tournament, Player, Stage, StagePlayer, Round, Match, MatchResult, get_pairing_strategy


class Command(BaseCommand):
    help = 'Test stage advancement functionality'

    def handle(self, *args, **options):
        # Create a fresh tournament for testing
        from django.contrib.auth.models import User
        
        owner, _ = User.objects.get_or_create(
            username='test_admin',
            defaults={'email': 'test@example.com'}
        )
        
        # Create a fresh tournament
        tournament = Tournament.objects.create(
            name='Test Stage Advancement Tournament',
            description='Testing stage advancement functionality',
            owner=owner
        )
        
        # Create some test players
        for i in range(4):
            user, _ = User.objects.get_or_create(
                username=f'testplayer{i+1}',
                defaults={'email': f'testplayer{i+1}@example.com'}
            )
            Player.objects.create(
                user=user,
                tournament=tournament,
                nickname=f'Player {i+1}'
            )
        
        # Create main stage and playoff stage
        tournament.create_initial_stage()
        tournament.create_playoff_stage(max_players=2)
        
        self.stdout.write(f'Testing with tournament: {tournament.name}')
        
        # Check current stage
        current_stage = tournament.get_current_stage()
        self.stdout.write(f'Current stage: {current_stage.name if current_stage else "None"}')
        
        # Check next stage
        next_stage = tournament.get_next_stage()
        self.stdout.write(f'Next stage: {next_stage.name if next_stage else "None"}')
        
        # Check if we can create rounds
        can_create_round = tournament.can_create_round_in_current_stage()
        self.stdout.write(f'Can create round in current stage: {can_create_round}')
        
        # Check if we can start next stage
        can_start_next = tournament.can_start_next_stage()
        self.stdout.write(f'Can start next stage: {can_start_next}')
        
        # Show current stage status
        if current_stage:
            self.stdout.write(f'Current stage complete: {current_stage.is_complete()}')
            current_round = current_stage.get_current_round()
            if current_round:
                self.stdout.write(f'Current round: {current_round.order}, complete: {current_round.is_complete()}')
            else:
                self.stdout.write('No rounds in current stage yet')
        
        # If we can create a round, let's create one for testing
        if can_create_round and not current_stage.rounds.exists():
            self.stdout.write('Creating first round for testing...')
            pairing_strategy = get_pairing_strategy(current_stage.pairing_strategy)
            new_round = Round.objects.create(stage=current_stage, order=1)
            pairing_strategy.make_pairings_for_round(new_round)
            self.stdout.write(f'Created round with {new_round.matches.count()} matches')
        
        self.stdout.write(self.style.SUCCESS('Stage advancement test completed'))