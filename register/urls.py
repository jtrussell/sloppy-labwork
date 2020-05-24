from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='home-register'),
    path('new/', views.add, name='register-add'),
    path('success/', views.add, name='register-add-success'),
    path('edit/', views.edit, name='register-edit'),
    path('verify/<int:id>/', views.verify, name='register-verify'),
]
