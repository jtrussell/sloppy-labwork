from django.urls import path
from . import views

app_name = 'design_system'

urlpatterns = [
    path('', views.index, name='index'),
    path('dialogs/demo/', views.dialog_demo, name='dialog-demo'),
    path('<slug:section_slug>/', views.section, name='section'),
]
