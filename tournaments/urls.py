from . import views
from django.urls import path


urlpatterns = [
    path('', views.TournamentList.as_view(), name='tournaments-list'),
    path('<int:pk>/edit', views.edit, name='tournaments-edit'),
    path('<int:pk>/sign-up', views.sign_up, name='tournaments-register'),
    path('<int:pk>/download', views.download, name='tournaments-download'),
    path('<int:pk>/', views.detail, name='tournaments-detail'),
    path('new/', views.add, name='tournaments-new'),
]
