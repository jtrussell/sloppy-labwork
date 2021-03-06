# Generated by Django 3.0 on 2020-06-21 07:19

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tournaments', '0005_auto_20200620_1247'),
    ]

    operations = [
        migrations.AddField(
            model_name='tournamentregistration',
            name='tournament',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, related_name='tournament_registrations', to='tournaments.Tournament'),
            preserve_default=False,
        ),
    ]
