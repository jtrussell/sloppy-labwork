from django.db import migrations
from django.utils.crypto import get_random_string

CODE_CHARACTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

SYSTEM_TEMPLATES = [
    {
        'system_key': 'triad',
        'name': 'Triad',
        'description': 'Bring three decks and ban one of theirs. Win a game with each of your two remaining decks.',
        'steps': [
            ('submit', 3, 'ineligible'),
            ('ban', 1, 'ineligible'),
            ('play', 1, 'losing_only'),
            ('play', 1, 'losing_only'),
            ('play', 1, 'losing_only'),
        ],
    },
    {
        'system_key': 'triad-bo1',
        'name': 'Triad Bo1',
        'description': 'Bring three decks, ban one of theirs, then play a single game.',
        'steps': [
            ('submit', 3, 'ineligible'),
            ('ban', 1, 'ineligible'),
            ('play', 1, 'ineligible'),
        ],
    },
    {
        'system_key': 'hexad',
        'name': 'Hexad',
        'description': 'Bring six decks. Ban one, safe one, ban another, then play three games without repeating a deck.',
        'steps': [
            ('submit', 6, 'ineligible'),
            ('ban', 1, 'ineligible'),
            ('safe', 1, 'ineligible'),
            ('ban', 1, 'ineligible'),
            ('play', 1, 'ineligible'),
            ('play', 1, 'ineligible'),
            ('play', 1, 'ineligible'),
        ],
    },
]


def generate_unused_code(SessionTemplate):
    while True:
        code = 'tst_' + get_random_string(6, allowed_chars=CODE_CHARACTERS)
        if not SessionTemplate.objects.filter(code=code).exists():
            return code


def seed_system_templates(apps, schema_editor):
    SessionTemplate = apps.get_model('trade_secrets', 'SessionTemplate')
    TemplateStep = apps.get_model('trade_secrets', 'TemplateStep')
    for definition in SYSTEM_TEMPLATES:
        template, created = SessionTemplate.objects.get_or_create(
            system_key=definition['system_key'],
            defaults={
                'name': definition['name'],
                'description': definition['description'],
                'code': generate_unused_code(SessionTemplate),
            },
        )
        if not created:
            continue
        TemplateStep.objects.bulk_create(
            TemplateStep(
                template=template, order=order, action=action,
                quantity=quantity, played_deck_rule=played_deck_rule)
            for order, (action, quantity, played_deck_rule) in enumerate(definition['steps'])
        )


def remove_unused_system_templates(apps, schema_editor):
    SessionTemplate = apps.get_model('trade_secrets', 'SessionTemplate')
    SessionTemplate.objects.filter(
        system_key__in=[definition['system_key'] for definition in SYSTEM_TEMPLATES],
        sessions__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('trade_secrets', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_system_templates, remove_unused_system_templates),
    ]
