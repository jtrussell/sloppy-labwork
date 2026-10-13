from django.conf import settings
from django.contrib.sites.models import Site
from django.urls import reverse


def absolute_url(url_name, *args):
    domain = Site.objects.get_current().domain
    return f'{settings.ACCOUNT_DEFAULT_HTTP_PROTOCOL}://{domain}{reverse(url_name, args=args)}'
