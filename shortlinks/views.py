from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render

from .models import ShortLink


def follow(request, slug):
    link = get_object_or_404(ShortLink, slug=slug, is_active=True)
    link.record_hit()

    if link.uses_fallback_page():
        response = render(request, 'shortlinks/fallback.html', {'link': link})
    else:
        response = HttpResponseRedirect(link.target_url)
        response.status_code = link.response_type

    response['Cache-Control'] = 'no-cache, max-age=0, must-revalidate'
    return response
