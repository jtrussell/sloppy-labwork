from django.urls import path

from . import views

urlpatterns = [
    path('', views.RegisterList.as_view(), name='register-home'),
    path('about/', views.about, name='register-about'),
    path('verify/<int:id>/', views.verify, name='register-verify'),
    path('review/<int:pk>/', views.review, name='register-review'),
    path('<int:pk>/', views.RegisterDetail.as_view(), name='register-detail'),
    path('<int:pk>/photo', views.RegisterPhoto.as_view(), name='register-photo'),
    path('new/', views.add, name='register-new'),
    path('success/', views.add, name='register-new-success'),
]
