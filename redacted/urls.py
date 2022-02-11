from django.urls import path
from . import views

urlpatterns = [
    path('random-access-archives', views.random_access_archives, name='redacted-random'),
]

