from django.db import migrations

SEED_FALLBACK_DOK_USERNAMES = ['jtrussell', 'quickdraw3457', 'catsmdogs']


def create_fallback_collections(apps, schema_editor):
    FallbackCollection = apps.get_model('redacted', 'FallbackCollection')
    for dok_username in SEED_FALLBACK_DOK_USERNAMES:
        FallbackCollection.objects.get_or_create(dok_username=dok_username)


def delete_fallback_collections(apps, schema_editor):
    FallbackCollection = apps.get_model('redacted', 'FallbackCollection')
    FallbackCollection.objects.filter(dok_username__in=SEED_FALLBACK_DOK_USERNAMES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('redacted', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_fallback_collections, delete_fallback_collections),
    ]
