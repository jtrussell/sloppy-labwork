# Generated by Django 5.0 on 2024-10-30 15:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user_profile', '0004_userprofile_discord_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='discord_id',
            field=models.BigIntegerField(blank=True, default=None, null=True, verbose_name='Discord ID'),
        ),
    ]
