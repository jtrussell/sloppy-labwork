from django.core.management.base import BaseCommand
from pmc.models import Playgroup
from django.utils.text import slugify


class Command(BaseCommand):
    help = 'Creates the Premiere Events global playgroup'

    def handle(self, *args, **options):
        self.stdout.write('Creating Premiere Events global playgroup... ', ending='')
        
        playgroup, created = Playgroup.objects.get_or_create(
            slug='premiere-events',
            defaults={
                'name': 'Premiere Events',
                'is_global': True,
                'description': 'Official KeyForge premiere events including store championships, vault tours, and other special tournaments.'
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS('Created!'))
            self.stdout.write(f'Global playgroup "{playgroup.name}" created with slug "{playgroup.slug}"')
        else:
            self.stdout.write(self.style.WARNING('Already exists'))
            self.stdout.write(f'Playgroup "{playgroup.name}" already exists')