from django.apps import AppConfig


class TourneyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tourney'

    def ready(self):
        from ghostform.hooks import register_form_usage_describer, register_response_access_check
        from . import signals
        from .result_forms import describe_tournaments_using_forms, user_administers_tournament_using_form

        register_response_access_check(user_administers_tournament_using_form)
        register_form_usage_describer(describe_tournaments_using_forms)
