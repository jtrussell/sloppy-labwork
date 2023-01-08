from django.urls import path
from . import views

urlpatterns = [
    path('', views.deck_simulator, name='deck-simulator'),
    path('<str:id>/', views.deck_info),
    path('my-decks', views.my_decks),
    path('proxy', views.proxy, name='deck-proxy'),
]
