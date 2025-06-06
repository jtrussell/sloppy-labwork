# Generated by Django 5.2 on 2025-05-22 01:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pmc', '0053_alter_achievement_criteria_alter_trophy_criteria'),
    ]

    operations = [
        migrations.AlterField(
            model_name='achievement',
            name='criteria',
            field=models.IntegerField(choices=[(0, 'Event Matches'), (1, 'Sealed Event Matches'), (2, 'Archon Event Matches'), (3, 'Alliance Event Matches'), (4, 'Adaptive Event Matches'), (5, 'Tournament Match Wins'), (6, 'Sealed Tournament Match Wins'), (7, 'Archon Tournament Match Wins'), (8, 'Alliance Tournament Match Wins'), (9, 'Adaptive Tournament Match Wins'), (10, 'Events')], default=0),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='trophy',
            name='criteria',
            field=models.IntegerField(choices=[(0, 'Event Matches'), (1, 'Sealed Event Matches'), (2, 'Archon Event Matches'), (3, 'Alliance Event Matches'), (4, 'Adaptive Event Matches'), (5, 'Tournament Match Wins'), (6, 'Sealed Tournament Match Wins'), (7, 'Archon Tournament Match Wins'), (8, 'Alliance Tournament Match Wins'), (9, 'Adaptive Tournament Match Wins'), (10, 'Events')], default=0),
            preserve_default=False,
        ),
    ]
