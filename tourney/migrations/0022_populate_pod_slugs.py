from django.db import migrations


def populate_pod_slugs(apps, schema_editor):
    from tourney.models import build_unique_pod_slugs

    Pod = apps.get_model('tourney', 'Pod')
    stage_ids = Pod.objects.filter(slug='').values_list('stage_id', flat=True).distinct()
    for stage_id in stage_ids:
        stage_pods = list(Pod.objects.filter(stage_id=stage_id).order_by('order', 'id'))
        for pod, slug in zip(stage_pods, build_unique_pod_slugs(pod.name for pod in stage_pods)):
            pod.slug = slug
            pod.save(update_fields=['slug'])


class Migration(migrations.Migration):

    dependencies = [
        ('tourney', '0021_rename_group_to_pod'),
    ]

    operations = [
        migrations.RunPython(populate_pod_slugs, migrations.RunPython.noop),
    ]
