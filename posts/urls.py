from . import views
from django.urls import path


urlpatterns = [
    path('', views.PostList.as_view(), name='posts-list'),
    path('new/', views.PostCreate.as_view(), name='posts-create'),
    path('preview/', views.MarkdownPreview.as_view(), name='posts-preview'),
    path('<slug:slug>/', views.PostDetail.as_view(), name='posts-detail'),
    path('<slug:slug>/edit/', views.PostUpdate.as_view(), name='posts-edit'),
    path('<slug:slug>/delete/', views.PostDelete.as_view(), name='posts-delete'),
]
