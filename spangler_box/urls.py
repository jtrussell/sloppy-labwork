from . import views
from django.urls import path


urlpatterns = [
    path('new-from-template/', views.create_from_template,
         name='spangler-from-template'),
    path('join/<str:key>/', views.join, name='spangler-join'),
    path('<int:pk>/', views.SecretDetail.as_view(), name='spangler-detail'),
]
