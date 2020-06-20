from . import views
from django.urls import path


urlpatterns = [
    path('', views.TournamentList.as_view(), name='tournaments-list'),
    path('edit/<int:pk>/', views.edit, name='tournaments-edit'),
    path('<int:pk>/', views.detail, name='tournaments-detail'),
    path('new/', views.add, name='tournaments-new'),
]
