from django.core.management.base import BaseCommand
from pmc.models import Playgroup
from django.utils.text import slugify


class Command(BaseCommand):
    help = 'Creates the Premier Events global playgroup'

    def handle(self, *args, **options):
        self.stdout.write(
            'Creating Premier Events global playgroup... ', ending='')

        playgroup, created = Playgroup.objects.get_or_create(
            slug='premier-events',
            defaults={
                'name': 'Premier Events',
                'is_global': True,
                'description': 'Official KeyForge premier events including store championships, vault tours, and other special tournaments.'
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS('Created!'))
            self.stdout.write(
                f'Global playgroup "{playgroup.name}" created with slug "{playgroup.slug}"')
        else:
            self.stdout.write(self.style.WARNING('Already exists'))
            self.stdout.write(f'Playgroup "{playgroup.name}" already exists')
