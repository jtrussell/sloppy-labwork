# Generated by Django 5.0 on 2025-01-25 22:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pmc', '0008_alter_playgroupmember_nickname'),
    ]

    operations = [
        migrations.AlterField(
            model_name='playgroupmember',
            name='nickname',
            field=models.CharField(blank=True, default=None, max_length=100, null=True),
        ),
    ]
