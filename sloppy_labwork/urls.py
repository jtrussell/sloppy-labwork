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
    path('decks/', include('decks.urls')),
    path('tournaments/', include('tournaments.urls')),
    path('redacted/', include('redacted.urls')),
    path('kagi-live/', include('transporter_platform.urls')),
    path('pmc/', include('pmc.urls')),
    path('admin/', admin.site.urls),

    # Common to all hosts
    path('accounts/', include('allauth.urls')),
]
