"""sloppy_labwork URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from . import views


urlpatterns = [
    path('', views.index, name='home'),
    path('contact/', views.contact, name='contact'),
    path('team/', views.the_team, name='the-team'),
    path('register/', include('register.urls')),
    path('ratings/', include('ratings.urls')),
    path('posts/', include('posts.urls')),
    path('profile/', include('user_profile.urls')),
    path('accounts/', include('allauth.urls')),
    path('decks/', include('decks.urls')),
    path('tournaments/', include('tournaments.urls')),
    path('redacted/', include('redacted.urls')),
    path('kagi-live/', include('transporter_platform.urls')),
    path('pmc/', include('pmc.urls')),
    path('admin/', admin.site.urls),
]
