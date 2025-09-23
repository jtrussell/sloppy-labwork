from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tourney.models import Tournament, Player, Stage, StagePlayer


class Command(BaseCommand):
    help = 'Create a sample tournament for testing'

    def handle(self, *args, **options):
        # Get or create a user to own the tournament
        owner, created = User.objects.get_or_create(
            username='tournament_admin',
            defaults={
                'email': 'admin@example.com',
                'first_name': 'Tournament',
                'last_name': 'Admin'
            }
        )
        
        if created:
            owner.set_password('password123')
            owner.save()
            self.stdout.write(f'Created user: {owner.username}')
        
        # Create tournament
        tournament = Tournament.objects.create(
            name='Sample Swiss Tournament',
            description='A sample tournament for testing the tournament runner',
            owner=owner,
            is_accepting_registrations=True
        )
        
        self.stdout.write(f'Created tournament: {tournament.name}')
        
        # Create some sample players
        sample_usernames = ['alice', 'bob', 'charlie', 'diana', 'eve', 'frank', 'grace', 'henry']
        
        for username in sample_usernames:
            user, user_created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@example.com',
                    'first_name': username.capitalize()
                }
            )
            
            if user_created:
                user.set_password('password123')
                user.save()
            
            player, player_created = Player.objects.get_or_create(
                user=user,
                tournament=tournament,
                defaults={'nickname': f'{username.capitalize()}'}
            )
            
            if player_created:
                self.stdout.write(f'Created player: {player.get_display_name()}')
        
        # Create initial stage
        stage = tournament.create_initial_stage()
        self.stdout.write(f'Created stage: {stage.name}')
        
        # Create a playoff stage for testing
        playoff_stage = tournament.create_playoff_stage(max_players=4)
        self.stdout.write(f'Created playoff stage: {playoff_stage.name}')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created sample tournament with {tournament.players.count()} players and {tournament.stages.count()} stages'
            )
        )