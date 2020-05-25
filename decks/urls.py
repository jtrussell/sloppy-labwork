from django.urls import path

from . import views

urlpatterns = [
    path('<id>/', views.deck_details, name='deck-detail'),
]
