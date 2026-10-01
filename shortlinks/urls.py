from django.urls import path
from . import views

urlpatterns = [
    path('<slug:slug>', views.follow, name='shortlinks-follow'),
    path('<slug:slug>/', views.follow),
]
