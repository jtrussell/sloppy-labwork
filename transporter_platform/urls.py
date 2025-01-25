
from django.urls import path

from . import views

urlpatterns = [
    path('play', views.kagi_live, name='kagi-live--play'),
    path('super-secret-sync', views.sync_matches_played),
]
