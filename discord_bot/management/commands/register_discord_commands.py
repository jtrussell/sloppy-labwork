import json
import os
import requests
from django.core.management.base import BaseCommand, CommandError
from discord_bot.registry import get_commands

DISCORD_API_BASE_URL = 'https://discord.com/api/v10'


class Command(BaseCommand):
    help = 'Overwrite the Discord slash commands registered for the Sloppy Labwork bot'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            '--guild',
            help='Register the commands for a single guild (instant) instead of globally (up to an hour to propagate)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print the command payload without sending it to Discord',
        )

    def handle(self, *args, **options):
        definitions = [command.definition for command in get_commands()]
        if options['dry_run']:
            self.stdout.write(json.dumps(definitions, indent=2))
            return

        app_id = os.environ.get('DISCORD_APP_ID')
        bot_token = os.environ.get('DISCORD_BOT_TOKEN')
        if not app_id or not bot_token:
            raise CommandError('DISCORD_APP_ID and DISCORD_BOT_TOKEN must be set')

        guild_id = options['guild']
        if guild_id:
            url = f'{DISCORD_API_BASE_URL}/applications/{app_id}/guilds/{guild_id}/commands'
            scope = f'guild {guild_id}'
        else:
            url = f'{DISCORD_API_BASE_URL}/applications/{app_id}/commands'
            scope = 'global'

        try:
            response = requests.put(
                url,
                json=definitions,
                headers={'Authorization': f'Bot {bot_token}'},
                timeout=30,
            )
        except requests.RequestException as e:
            raise CommandError(f'Could not reach Discord: {e}')
        if not response.ok:
            raise CommandError(
                f'Discord responded {response.status_code}: {response.text}')

        registered = response.json()
        for command in registered:
            self.stdout.write(f"  /{command['name']} ({command['id']})")
        self.stdout.write(self.style.SUCCESS(
            f'Registered {len(registered)} {scope} command(s)'))
