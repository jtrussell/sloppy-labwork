from django.urls import path
from . import views

urlpatterns = [
    path('pg/<slug:slug>/', views.PlaygroupDetail.as_view(), name='pmc-pg-detail'),
    path('pg/<slug:slug>/@me/', views.my_playgroup_profile, name='pmc-my-pg'),
    path('pg/<slug:slug>/@me/manage',
         views.manage_my_playgroup_profile, name='pmc-my-pg-manage'),
    path('pg/<slug:slug>/members',
         views.PlaygroupMembersList.as_view(), name='pmc-pg-members'),
    path('pg/<slug:slug>/members/<username>',
         views.PlaygroupMemberDetail.as_view(), name='pmc-pg-member-detail'),
    path('pg/<slug:slug>/members/<username>/manage',
         views.PlaygroupMemberManage.as_view(), name='pmc-pg-member-manage'),
    path('pg/<slug:slug>/leaderboard',
         views.playgroup_leaderboard, name='pmc-pg-leaderboard'),
    path('pg/<slug:slug>/events',
         views.PlaygroupEventsList.as_view(), name='pmc-pg-events'),
    path('pg/<slug:slug>/events/new',
         views.submit_event_results, name='pmc-pg-events-new'),
    path('pg/<slug:slug>/events/<int:pk>',
         views.EventDetail.as_view(), name='pmc-event-detail'),
    path('pg/<slug:slug>/events/<int:pk>/manage',
         views.event_manage, name='pmc-event-manage'),
    path('typography', views.typography),
]
