from django.contrib import admin
from django.urls import include, path
from . import views
from common.urls import urlpatterns as common_urlpatterns

urlpatterns = [
    path('', views.index, name='home'),
    path('contact/', views.contact, name='contact'),
    path('team/', views.the_team, name='the-team'),
    path('register/', include('register.urls')),
    path('ratings/', include('ratings.urls')),
    path('posts/', include('posts.urls')),
    path('@me/', include('user_profile.urls')),
    path('decks/', include('decks.urls')),
    path('redacted/', include('redacted.urls')),
    path('kagi-live/', include('transporter_platform.urls')),
    path('pmc/', include('pmc.urls')),
    path('tourney/', include('tourney.urls')),
    path('timer/', include('timekeeper.urls')),

    # Common to all hosts
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
]

urlpatterns += common_urlpatterns
