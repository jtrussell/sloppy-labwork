from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from .models import Playgroup
from .models import PlaygroupMember
from .models import Feature


def _get_playgroup_slug(request):
    chunks = request.path.split('/')
    playgroup_slug = None
    while len(chunks):
        chunk = chunks.pop(0)
        if chunk == 'pg':
            playgroup_slug = chunks.pop(0)
    return playgroup_slug


def _should_show_ladders_link(request, playgroup):
    if playgroup.is_global or not request.user.is_authenticated:
        return False
    if not playgroup.has_feature(Feature.Keys.LADDERS):
        return False
    viewer_member = PlaygroupMember.objects.filter(
        playgroup=playgroup, user=request.user).first()
    if viewer_member is None:
        return False
    return viewer_member.is_staff or playgroup.ladders.exists()


def nav_links(request):
    playgroup_slug = _get_playgroup_slug(request)
    nav_links = []

    nav_links.append({
        'name': _('My KeyChain'),
        'url': reverse('pmc-my-keychain'),
        'is_active': False,
    })

    if playgroup_slug:
        try:
            current_playgroup = Playgroup.objects.get(slug=playgroup_slug)
        except Playgroup.DoesNotExist:
            current_playgroup = None

        nav_links.append({
            'name': _('Home'),
            'url': reverse('pmc-pg-detail', args=[playgroup_slug]),
            'is_active': False,
        })

        nav_links.append({
            'name': _('Events'),
            'url': reverse('pmc-pg-events', args=[playgroup_slug]),
            'is_active': False,
        })

        # Only show Members nav for non-global playgroups
        if current_playgroup and not current_playgroup.is_global:
            nav_links.append({
                'name': _('Members'),
                'url': reverse('pmc-pg-members', args=[playgroup_slug]),
                'is_active': False,
            })

        if current_playgroup and _should_show_ladders_link(request, current_playgroup):
            nav_links.append({
                'name': _('Ladders'),
                'url': reverse('pmc-pg-ladders', args=[playgroup_slug]),
                'is_active': False,
            })

        nav_links.append({
            'name': _('Leaderboards'),
            'url': reverse('pmc-pg-leaderboard', args=[playgroup_slug]),
            'is_active': False,
        })

    if not playgroup_slug:
        # nav_links.append({
        #    'name': _('Find'),
        #    'url': reverse('pmc-finder'),
        #    'is_active': False,
        # })

        nav_links.append({
            'name': _('Leaderboards'),
            'url': reverse('pmc-leaderboard'),
            'is_active': False,
        })

        nav_links.append({
            'name': _('Results'),
            'url': reverse('pmc-my-results'),
            'is_active': False,
        })

        nav_links.append({
            'name': _('Awards'),
            'url': reverse('pmc-my-awards'),
            'is_active': False,
        })

        nav_links.append({
            'name': _('News'),
            'url': 'https://keychaining.substack.com/',
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
    try:
        return {'playgroup': Playgroup.objects.get(slug=playgroup_slug)} if playgroup_slug else {}
    except Playgroup.DoesNotExist:
        return {}


def playgroup_member(request):
    playgroup_slug = _get_playgroup_slug(request)
    try:
        return {'playgroup_member': PlaygroupMember.objects.get(
            playgroup__slug=playgroup_slug,
            user=request.user
        )} if playgroup_slug and request.user else {}
    except PlaygroupMember.DoesNotExist:
        return {}
    except TypeError:
        return {}


def playgroup_features(request):
    playgroup_slug = _get_playgroup_slug(request)
    playgroup = Playgroup.objects.filter(slug=playgroup_slug).first() if playgroup_slug else None
    return {'pg_features': playgroup.get_enabled_feature_keys() if playgroup else set()}


def pmc_profile(request):
    return {
        'my_profile': request.user.pmc_profile if request.user.is_authenticated else None,
        'my_avatar': request.user.pmc_profile.get_avatar() if request.user.is_authenticated else None,
        'my_background': request.user.pmc_profile.get_background() if request.user.is_authenticated else None,
    }
