from django.urls import path

from . import views

app_name = 'trade_secrets'

urlpatterns = [
    path('', views.home, name='home'),
    path('templates/new/', views.template_create, name='template-create'),
    path('templates/<str:template_code>/', views.template_detail, name='template-detail'),
    path('templates/<str:template_code>/archive/', views.template_archive, name='template-archive'),
    path('templates/<str:template_code>/visibility/', views.template_visibility, name='template-visibility'),
    path('templates/<str:template_code>/delete/', views.template_delete, name='template-delete'),
    path('sessions/new/', views.session_create, name='session-create'),
    path('lineup-versions/', views.lineup_versions, name='lineup-versions'),
    path('lineup-preview/', views.lineup_preview, name='lineup-preview'),
    path('<str:session_code>/', views.session_detail, name='session-detail'),
    path('<str:session_code>/poll/', views.session_poll, name='session-poll'),
    path('<str:session_code>/join/', views.session_join, name='session-join'),
    path('<str:session_code>/decks/', views.session_decks, name='session-decks'),
    path('<str:session_code>/pick/', views.session_pick, name='session-pick'),
    path('<str:session_code>/games/<int:step_order>/result/', views.session_result, name='session-result'),
    path('<str:session_code>/games/<int:step_order>/result/reset/', views.session_result_reset,
         name='session-result-reset'),
]
