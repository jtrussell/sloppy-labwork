# Generated by Django 5.0 on 2025-02-09 11:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pmc', '0013_alter_rankingpointsmap_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='player_count',
            field=models.SmallIntegerField(blank=True, default=None, null=True),
        ),
    ]
