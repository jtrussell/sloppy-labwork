# Generated by Django 5.0 on 2025-03-16 13:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pmc', '0036_pmcprofile_mv_username'),
    ]

    operations = [
        migrations.AddField(
            model_name='background',
            name='artist_credit',
            field=models.CharField(blank=True, default=None, max_length=100, null=True),
        ),
    ]
