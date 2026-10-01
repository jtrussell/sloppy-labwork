from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import ShortLink, validate_redirect_target


class RedirectTargetValidatorTest(TestCase):
    def test_accepts_absolute_http_urls(self):
        validate_redirect_target('https://example.com/path?x=1')
        validate_redirect_target('http://example.com')

    def test_accepts_same_site_paths(self):
        validate_redirect_target('/pmc/@me/')

    def test_rejects_unsafe_or_schemeless_values(self):
        for value in ['javascript:alert(1)', 'example.com', 'ftp://example.com', '//evil.com']:
            with self.assertRaises(ValidationError, msg=value):
                validate_redirect_target(value)


class FollowShortLinkTest(TestCase):
    target = 'https://example.com/landing'

    def create_link(self, slug='foo', **kwargs):
        return ShortLink.objects.create(slug=slug, target_url=self.target, **kwargs)

    def test_each_redirect_status_code_is_honored(self):
        for response_type in [301, 302, 307, 308]:
            slug = f'code-{response_type}'
            self.create_link(slug=slug, response_type=response_type)
            response = self.client.get(f'/r/{slug}')
            self.assertEqual(response.status_code, response_type)
            self.assertEqual(response['Location'], self.target)

    def test_trailing_slash_is_accepted(self):
        self.create_link()
        response = self.client.get('/r/foo/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], self.target)

    def test_responses_are_not_cacheable(self):
        self.create_link(response_type=ShortLink.ResponseType.MOVED_PERMANENTLY)
        response = self.client.get('/r/foo')
        self.assertEqual(response['Cache-Control'], 'no-cache, max-age=0, must-revalidate')

    def test_fallback_page_renders_meta_refresh_and_script(self):
        self.create_link(response_type=ShortLink.ResponseType.FALLBACK_PAGE)
        response = self.client.get('/r/foo')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Location', response)
        self.assertContains(response, f'content="0;url={self.target}"')
        self.assertContains(response, f'window.location.replace("{self.target}")')

    def test_fallback_page_escapes_target_in_script(self):
        link = self.create_link(response_type=ShortLink.ResponseType.FALLBACK_PAGE)
        link.target_url = 'https://example.com/?q="</script><script>alert(1)</script>'
        link.save()
        response = self.client.get('/r/foo')
        self.assertNotContains(response, '</script><script>alert(1)')

    def test_unknown_slug_is_404(self):
        response = self.client.get('/r/nope')
        self.assertEqual(response.status_code, 404)

    def test_inactive_link_is_404(self):
        self.create_link(is_active=False)
        response = self.client.get('/r/foo')
        self.assertEqual(response.status_code, 404)

    def test_hits_are_counted_without_touching_updated_on(self):
        link = self.create_link()
        self.client.get('/r/foo')
        self.client.get('/r/foo')
        link.refresh_from_db()
        self.assertEqual(link.hit_count, 2)
        self.assertEqual(link.updated_on, link.created_on)
