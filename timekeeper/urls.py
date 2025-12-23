from django.urls import path
from . import views

app_name = 'timekeeper'

urlpatterns = [
    path('create/', views.timer_create, name='timer_create'),
    path('<str:timer_code>/', views.timer_detail, name='timer_detail'),
    path('<str:timer_code>/full/', views.timer_full_page, name='timer_full_page'),
    path('<str:timer_code>/start/', views.timer_start, name='timer_start'),
    path('<str:timer_code>/pause/', views.timer_pause, name='timer_pause'),
    path('<str:timer_code>/add/', views.timer_add_time, name='timer_add_time'),
    path('<str:timer_code>/subtract/', views.timer_subtract_time, name='timer_subtract_time'),
    path('<str:timer_code>/set/', views.timer_set_time, name='timer_set_time'),
    path('<str:timer_code>/delete/', views.timer_delete, name='timer_delete'),
]
