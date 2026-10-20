from django.db import migrations

BOX_LEAGUES_FEATURE_KEY = 'box-leagues'


def create_box_leagues_feature(apps, schema_editor):
    Feature = apps.get_model('pmc', 'Feature')
    Feature.objects.get_or_create(
        key=BOX_LEAGUES_FEATURE_KEY,
        defaults={
            'name': 'Box Leagues',
            'description': 'Recurring sessions of small round-robin boxes with promotion and relegation.',
            'is_enabled': False,
        },
    )


def delete_box_leagues_feature(apps, schema_editor):
    Feature = apps.get_model('pmc', 'Feature')
    Feature.objects.filter(key=BOX_LEAGUES_FEATURE_KEY).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pmc', '0102_box_leagues'),
    ]

    operations = [
        migrations.RunPython(create_box_leagues_feature, delete_box_leagues_feature),
    ]
