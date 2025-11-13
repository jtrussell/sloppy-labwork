from django.urls import path
from . import views

urlpatterns = [
    path('', views.list, name='redacted-list'),
    path('discord-webhook/', views.discord_webhook_ingress),
    path('random-access-archives/',
         views.random_access_archives, name='redacted-random'),
    path('shard-of-knowledge/', views.shard_of_knowledge,
         name='redacted-knowledge'),
]
