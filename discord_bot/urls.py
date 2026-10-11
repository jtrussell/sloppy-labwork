from django.urls import path
from . import views

urlpatterns = [
    path('interactions/', views.interactions, name='discord-interactions'),
]
