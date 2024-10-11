
from django.urls import path

from . import views

urlpatterns = [
    path('kagi-live', views.kagi_live, name='tp-kagi-live'),
]
