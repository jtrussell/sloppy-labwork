from django.urls import path
from . import views

app_name = 'ghostform'

urlpatterns = [
    path('', views.form_list, name='ghostform-list'),
    path('new/', views.form_create, name='ghostform-create'),
    path('picker/results/', views.form_picker_results,
         name='ghostform-picker-results'),
    path('picker/preview/<str:form_code>/', views.form_picker_preview,
         name='ghostform-picker-preview'),
    path('feed/<uuid:feed_token>.json', views.form_responses_feed_json,
         name='ghostform-responses-feed-json'),
    path('feed/<uuid:feed_token>.xml', views.form_responses_feed_xml,
         name='ghostform-responses-feed-xml'),
    path('f/<str:form_code>/', views.form_fill, name='ghostform-fill'),
    path('f/<str:form_code>/thanks/', views.form_fill_thanks,
         name='ghostform-fill-thanks'),
    path('<str:form_code>/', views.form_detail, name='ghostform-detail'),
    path('<str:form_code>/edit/', views.form_edit, name='ghostform-edit'),
    path('<str:form_code>/status/', views.form_update_status,
         name='ghostform-update-status'),
    path('<str:form_code>/responses.csv', views.form_responses_csv,
         name='ghostform-responses-csv'),
    path('<str:form_code>/feed/', views.form_update_feed,
         name='ghostform-update-feed'),
]
