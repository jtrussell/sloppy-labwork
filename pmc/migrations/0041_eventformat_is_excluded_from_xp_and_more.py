# Generated by Django 5.0 on 2025-03-31 02:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pmc', '0040_playgrouptype_playgroup_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventformat',
            name='is_excluded_from_xp',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='playgrouptype',
            name='description',
            field=models.CharField(blank=True, default='## Welcome!\n\nEOs may customize this space.', max_length=200, null=True),
        ),
    ]
