from django.urls import path
from . import views

urlpatterns = [
    path('', views.my_list, name='spangler-my-list'),
]


