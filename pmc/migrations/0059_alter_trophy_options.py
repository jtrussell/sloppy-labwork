# Generated by Django 5.2 on 2025-05-30 13:33

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pmc', '0058_alter_achievement_criteria_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='trophy',
            options={'ordering': ('sort_order', 'name'), 'verbose_name_plural': 'Trophies'},
        ),
    ]
