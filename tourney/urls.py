from django.urls import path
from . import views

urlpatterns = [
    path('', views.my_tournaments, name='tourney-my-tournaments'),
    path('create/', views.create_tournament, name='tourney-create-tournament'),
    path('<int:tournament_id>/', views.tournament_detail_home, name='tourney-detail-home'),
    path('<int:tournament_id>/matches/', views.tournament_detail_matches, name='tourney-detail-matches'),
    path('<int:tournament_id>/standings/', views.tournament_detail_standings, name='tourney-detail-standings'),
    path('<int:tournament_id>/edit/', views.edit_tournament, name='tourney-edit-tournament'),
    path('<int:tournament_id>/players/', views.manage_players, name='tourney-manage-players'),
    path('<int:tournament_id>/register/', views.register_for_tournament, name='tourney-register'),
    path('<int:tournament_id>/unregister/', views.unregister_from_tournament, name='tourney-unregister'),
    path('<int:tournament_id>/drop/', views.drop_from_tournament, name='tourney-drop'),
    path('<int:tournament_id>/undrop/', views.undrop_from_tournament, name='tourney-undrop'),
    path('<int:tournament_id>/round/create/', views.create_round, name='tourney-create-round'),
    path('<int:tournament_id>/round/delete/', views.delete_latest_round, name='tourney-delete-latest-round'),
    path('<int:tournament_id>/stage/advance/', views.start_next_stage, name='tourney-start-next-stage'),
    path('<int:tournament_id>/match/<int:match_id>/report/', views.report_match_result, name='tourney-report-result'),
    path('<int:tournament_id>/match/<int:match_id>/delete/', views.delete_match, name='tourney-delete-match'),
    path('<int:tournament_id>/match/add/', views.add_match, name='tourney-add-match'),
]