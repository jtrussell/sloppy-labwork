from django.urls import path
from . import views

urlpatterns = [
    path('', views.lineup_list, name='lineups-list'),
    path('new/', views.lineup_create, name='lineups-create'),
    path('<str:lineup_code>/', views.lineup_detail, name='lineups-detail'),
    path('<str:lineup_code>/edit/', views.lineup_edit, name='lineups-edit'),
    path('<str:lineup_code>/delete/', views.lineup_delete, name='lineups-delete'),

    path('<str:lineup_code>/notes/add/',
         views.lineup_note_add, name='lineups-note-add'),
    path('<str:lineup_code>/notes/<int:note_id>/edit/',
         views.lineup_note_edit, name='lineups-note-edit'),
    path('<str:lineup_code>/notes/<int:note_id>/delete/',
         views.lineup_note_delete, name='lineups-note-delete'),

    path('<str:lineup_code>/versions/new/',
         views.version_create, name='lineups-version-create'),

    path('versions/<str:version_code>/',
         views.version_detail, name='lineups-version-detail'),
    path('versions/<str:version_code>/edit/',
         views.version_edit, name='lineups-version-edit'),
    path('versions/<str:version_code>/delete/',
         views.version_delete, name='lineups-version-delete'),

    path('versions/<str:version_code>/notes/add/',
         views.version_note_add, name='lineups-version-note-add'),
    path('versions/<str:version_code>/notes/<int:note_id>/edit/',
         views.version_note_edit, name='lineups-version-note-edit'),
    path('versions/<str:version_code>/notes/<int:note_id>/delete/',
         views.version_note_delete, name='lineups-version-note-delete'),

    path('versions/<str:version_code>/decks/add/',
         views.version_deck_add, name='lineups-version-deck-add'),
    path('versions/<str:version_code>/decks/<int:deck_id>/remove/',
         views.version_deck_remove, name='lineups-version-deck-remove'),
    path('versions/<str:version_code>/decks/reorder/',
         views.version_deck_reorder, name='lineups-version-deck-reorder'),
]
