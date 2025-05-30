# Generated by Django 5.0 on 2025-01-28 11:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pmc', '0007_alter_eventresult_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='playgroupmember',
            name='house_flair',
            field=models.IntegerField(blank=True, choices=[(1, 'Brobnar'), (2, 'Dis'), (3, 'Ekwidon'), (4, 'Geistoid'), (5, 'Logos'), (6, 'Mars'), (7, 'Redemption'), (8, 'Sanctum'), (9, 'Saurian'), (10, 'Shadows'), (11, 'Skyborn'), (12, 'Star Alliance'), (13, 'Unfathomable'), (14, 'Untamed')], default=None, null=True),
        ),
        migrations.AddField(
            model_name='playgroupmember',
            name='tag_line',
            field=models.CharField(blank=True, default=None, max_length=100, null=True),
        ),
    ]
