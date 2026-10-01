from django.core.validators import URLValidator
from django.db import models
from django.db.models import F
from django.utils.translation import gettext_lazy as _


def validate_redirect_target(value):
    if value.startswith('/') and not value.startswith('//'):
        return
    URLValidator(schemes=['http', 'https'])(value)


class ShortLink(models.Model):
    class ResponseType(models.IntegerChoices):
        FALLBACK_PAGE = 200, _('Fallback page (meta refresh + JavaScript)')
        MOVED_PERMANENTLY = 301, _('301 Moved Permanently')
        FOUND = 302, _('302 Found')
        TEMPORARY_REDIRECT = 307, _('307 Temporary Redirect')
        PERMANENT_REDIRECT = 308, _('308 Permanent Redirect')

    slug = models.SlugField(max_length=100, unique=True)
    target_url = models.CharField(
        max_length=2000, validators=[validate_redirect_target])
    response_type = models.PositiveSmallIntegerField(
        choices=ResponseType.choices, default=ResponseType.FOUND)
    is_active = models.BooleanField(default=True)
    hit_count = models.PositiveIntegerField(default=0)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['slug']

    def __str__(self):
        return f'/r/{self.slug} -> {self.target_url}'

    def uses_fallback_page(self):
        return self.response_type == self.ResponseType.FALLBACK_PAGE

    def record_hit(self):
        ShortLink.objects.filter(pk=self.pk).update(
            hit_count=F('hit_count') + 1)
