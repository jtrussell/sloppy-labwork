# Generated by Django 5.0 on 2024-10-30 15:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user_profile', '0003_userprofile_dok_handle'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='discord_id',
            field=models.IntegerField(blank=True, default=None, null=True, verbose_name='Discord ID'),
        ),
    ]
