# Generated by Django 3.0.7 on 2021-01-21 01:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('register', '0012_auto_20200728_0141'),
    ]

    operations = [
        migrations.AddField(
            model_name='deckregistration',
            name='is_archived',
            field=models.BooleanField(default=False),
        ),
    ]
