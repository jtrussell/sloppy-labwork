from django.urls import include, path
from . import views


urlpatterns = [
    path('', views.index, name='profile'),
    path('delete/', views.delete_account, name='delete_account'),
]
