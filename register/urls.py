from django.urls import path

from . import views

urlpatterns = [
    path('', views.RegisterList.as_view(), name='register-home'),
    path('about/', views.about, name='register-about'),
    path('detail/<int:pk>/', views.RegisterDetail.as_view(), name='register-detail'),
    path('new/', views.add, name='register-add'),
    path('success/', views.add, name='register-add-success'),
    path('verify/<int:id>/', views.verify, name='register-verify'),
]
