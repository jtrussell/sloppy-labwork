from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from .models import Playgroup
from .models import PlaygroupMember


def _get_playgroup_slug(request):
    chunks = request.path.split('/')
    playgroup_slug = None
    while len(chunks):
        chunk = chunks.pop(0)
        if chunk == 'pg':
            playgroup_slug = chunks.pop(0)
    return playgroup_slug


def nav_links(request):
    playgroup_slug = _get_playgroup_slug(request)
    nav_links = []

    if playgroup_slug:
        nav_links.append({
            'name': _('Home'),
            'url': reverse('pmc-pg-detail', args=[playgroup_slug]),
            'is_active': False,
        })

        nav_links.append({
            'name': _('My KeyChain'),
            'url': reverse('pmc-my-pg', args=[playgroup_slug]),
            'is_active': False,
        })

        nav_links.append({
            'name': _('Events'),
            'url': reverse('pmc-pg-events', args=[playgroup_slug]),
            'is_active': False,
        })

        nav_links.append({
            'name': _('Members'),
            'url': reverse('pmc-pg-members', args=[playgroup_slug]),
            'is_active': False,
        })

        nav_links.append({
            'name': _('Leaderboard'),
            'url': reverse('pmc-pg-leaderboard', args=[playgroup_slug]),
            'is_active': False,
        })

    longest_matched_path = ''
    for link in nav_links:
        if request.path.startswith(link['url']) and len(link['url']) > len(longest_matched_path):
            longest_matched_path = link['url']

    for link in nav_links:
        if link['url'] == longest_matched_path:
            link['is_active'] = True

    return {'nav_links': nav_links}


def playgroup(request):
    playgroup_slug = _get_playgroup_slug(request)
    return {'playgroup': Playgroup.objects.get(slug=playgroup_slug)} if playgroup_slug else {}


def playgroup_member(request):
    playgroup_slug = _get_playgroup_slug(request)
    return {'playgroup_member': PlaygroupMember.objects.get(
        playgroup__slug=playgroup_slug,
        user=request.user
    )} if playgroup_slug and request.user else {}
