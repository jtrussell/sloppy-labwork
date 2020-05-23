from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='home-register'),
    path('new/', views.add, name='register-add'),
    path('edit/', views.edit, name='register-edit'),
]
