# Generated by Django 3.0 on 2020-05-24 03:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('register', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='deckregistration',
            name='verified_on',
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
    ]
