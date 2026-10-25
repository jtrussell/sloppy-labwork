from django.db import migrations
from django.utils.crypto import get_random_string

CODE_CHARACTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

EXCHANGE = {
    'system_key': 'exchange',
    'name': 'Exchange',
    'description': 'Bring two decks, then each player steals one of the other\'s. Win a game with both decks in your lineup.',
    'steps': [
        ('submit', 2, 'ineligible'),
        ('steal', 1, 'ineligible'),
        ('play', 1, 'losing_only'),
        ('play', 1, 'losing_only'),
        ('play', 1, 'ineligible'),
    ],
}


def generate_unused_code(SessionTemplate):
    while True:
        code = 'tst_' + get_random_string(6, allowed_chars=CODE_CHARACTERS)
        if not SessionTemplate.objects.filter(code=code).exists():
            return code


def seed_exchange_template(apps, schema_editor):
    SessionTemplate = apps.get_model('trade_secrets', 'SessionTemplate')
    TemplateStep = apps.get_model('trade_secrets', 'TemplateStep')
    template, created = SessionTemplate.objects.get_or_create(
        system_key=EXCHANGE['system_key'],
        defaults={
            'name': EXCHANGE['name'],
            'description': EXCHANGE['description'],
            'code': generate_unused_code(SessionTemplate),
        },
    )
    if not created:
        return
    TemplateStep.objects.bulk_create(
        TemplateStep(
            template=template, order=order, action=action,
            quantity=quantity, played_deck_rule=played_deck_rule)
        for order, (action, quantity, played_deck_rule) in enumerate(EXCHANGE['steps'])
    )


def remove_unused_exchange_template(apps, schema_editor):
    SessionTemplate = apps.get_model('trade_secrets', 'SessionTemplate')
    SessionTemplate.objects.filter(system_key=EXCHANGE['system_key'], sessions__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('trade_secrets', '0006_template_visibility'),
    ]

    operations = [
        migrations.RunPython(seed_exchange_template, remove_unused_exchange_template),
    ]
