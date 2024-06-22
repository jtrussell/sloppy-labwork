from . import views
from django.urls import path


urlpatterns = [
    path('new-from-template', views.create_from_template,
         name='spangler-from-template'),
]
