from django.urls import path
from . import views

urlpatterns = [
    path('', views.deck_simulator, name='deck-simulator'),
    path('<str:id>/', views.deck_info, name='generated-deck-page'),
    path('my-decks', views.my_decks, name='my-generated-decks'),
    path('<str:id>/proxy', views.proxy, name='generated-deck-proxy'),
]
