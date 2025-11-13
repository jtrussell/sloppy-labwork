from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Save existing users to trigger profile creation'

    def handle(self, *args, **options):
        self.stdout.write('Initializing PMC profiles...', ending='')
        for user in User.objects.all():
            user.save()
        self.stdout.write(
            self.style.SUCCESS('Done.')
        )
