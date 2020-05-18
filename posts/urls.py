from . import views
from django.urls import path


urlpatterns = [
    path('', views.PostList.as_view(), name='posts-list'),
    path('<slug:slug>/', views.PostDetail.as_view(), name='posts-detail'),
]