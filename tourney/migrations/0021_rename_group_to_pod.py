import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tourney', '0020_add_stageplayer_tiebreaker_value'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Group',
            new_name='Pod',
        ),
        migrations.RenameField(
            model_name='stageplayer',
            old_name='group',
            new_name='pod',
        ),
        migrations.AlterField(
            model_name='pod',
            name='stage',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pods', to='tourney.stage'),
        ),
        migrations.AlterField(
            model_name='stageplayer',
            name='pod',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stage_players', to='tourney.pod'),
        ),
        migrations.AlterModelOptions(
            name='pod',
            options={'ordering': ['order', 'id']},
        ),
        migrations.AddField(
            model_name='pod',
            name='order',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='pod',
            name='slug',
            field=models.SlugField(blank=True, default='', max_length=210),
        ),
        migrations.AlterField(
            model_name='tournamentactionlog',
            name='action_type',
            field=models.CharField(choices=[('create_tournament', 'Create Tournament'), ('add_player', 'Add Player'), ('drop_player', 'Drop Player'), ('undrop_player', 'Undrop Player'), ('create_round', 'Create Round'), ('advance_stage', 'Advance Stage'), ('report_result', 'Report Result'), ('update_result', 'Update Result'), ('delete_round', 'Delete Round'), ('register_player', 'Register Player'), ('unregister_player', 'Unregister Player'), ('move_player', 'Move Player')], max_length=20),
        ),
    ]
