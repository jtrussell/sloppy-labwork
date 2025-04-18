# Generated by Django 5.0 on 2025-01-15 14:09

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pmc', '0003_event'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='name',
            field=models.CharField(default='Test Event', max_length=200),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='event',
            name='start_date',
            field=models.DateField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='EventResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('finishing_position', models.PositiveSmallIntegerField(blank=True, default=None, null=True)),
                ('num_wins', models.PositiveSmallIntegerField(blank=True, default=None, null=True)),
                ('num_losses', models.PositiveSmallIntegerField(blank=True, default=None, null=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pmc.event')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='PlaygroupEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='playgroup_events', to='pmc.event')),
                ('playgroup', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='playgroup_events', to='pmc.playgroup')),
            ],
            options={
                'unique_together': {('playgroup', 'event')},
            },
        ),
        migrations.AddField(
            model_name='playgroup',
            name='events',
            field=models.ManyToManyField(related_name='playgroups', through='pmc.PlaygroupEvent', to='pmc.event'),
        ),
    ]
