from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Post


FAST_PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
SIMPLE_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


def grant_post_permissions(user, *codenames):
    user.user_permissions.add(
        *Permission.objects.filter(content_type__app_label='posts', codename__in=codenames))


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class PostTestCase(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(username='author', password='pw')
        self.reader = User.objects.create_user(username='reader', password='pw')
        self.editor = User.objects.create_user(username='editor', password='pw', is_staff=True)
        grant_post_permissions(self.editor, 'add_post', 'change_post', 'delete_post')
        self.published = Post.objects.create(
            title='Published Post', slug='published-post', author=self.author,
            content='Published body', published_on=timezone.now(), status=1)
        self.draft = Post.objects.create(
            title='Draft Post', slug='draft-post', author=self.author,
            content='Draft body', published_on=timezone.now(), status=0)


class PostVisibilityTests(PostTestCase):
    def test_list_hides_drafts_from_readers(self):
        self.client.force_login(self.reader)
        response = self.client.get(reverse('posts-list'))
        self.assertContains(response, 'Published Post')
        self.assertNotContains(response, 'Draft Post')
        self.assertNotContains(response, 'Edit post')

    def test_list_shows_drafts_and_actions_to_editors(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse('posts-list'))
        self.assertContains(response, 'Draft Post')
        self.assertContains(response, 'badge--warning">Draft')
        self.assertContains(response, reverse('posts-edit', args=['draft-post']))
        self.assertContains(response, reverse('posts-delete', args=['draft-post']))
        self.assertContains(response, reverse('posts-create'))

    def test_draft_detail_is_not_found_for_readers(self):
        self.client.force_login(self.reader)
        response = self.client.get(reverse('posts-detail', args=['draft-post']))
        self.assertEqual(response.status_code, 404)

    def test_draft_detail_is_visible_to_editors(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse('posts-detail', args=['draft-post']))
        self.assertContains(response, 'Draft body')
        self.assertContains(response, 'Edit post')

    def test_list_uses_summary_markdown_when_present(self):
        self.published.summary = 'A **bold** blurb'
        self.published.save()
        response = self.client.get(reverse('posts-list'))
        self.assertContains(response, '<strong>bold</strong>')

    def test_list_falls_back_to_squeezed_content(self):
        response = self.client.get(reverse('posts-list'))
        self.assertContains(response, 'Published body...')

    def test_list_shows_featured_image(self):
        self.published.featured_image_url = 'https://example.com/image.png'
        self.published.featured_image_alt = 'A shiny deck'
        self.published.save()
        response = self.client.get(reverse('posts-list'))
        self.assertContains(response, 'src="https://example.com/image.png" alt="A shiny deck"')


class PostEditingTests(PostTestCase):
    def post_data(self, **overrides):
        return {
            'title': 'Fresh Post',
            'slug': '',
            'status': 1,
            'published_on': '2026-10-01T12:00',
            'featured_image_url': '',
            'featured_image_alt': '',
            'summary': '',
            'content': 'Fresh body',
            **overrides,
        }

    def test_readers_cannot_reach_editing_pages(self):
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(reverse('posts-create')).status_code, 403)
        self.assertEqual(self.client.get(reverse('posts-edit', args=['published-post'])).status_code, 403)
        self.assertEqual(self.client.post(reverse('posts-delete', args=['published-post'])).status_code, 403)
        self.assertEqual(self.client.post(reverse('posts-preview'), {'markdown': 'x'}).status_code, 403)
        self.assertTrue(Post.objects.filter(slug='published-post').exists())

    def test_create_sets_author_and_slug_from_title(self):
        self.client.force_login(self.editor)
        response = self.client.post(reverse('posts-create'), self.post_data())
        post = Post.objects.get(title='Fresh Post')
        self.assertRedirects(response, reverse('posts-detail', args=['fresh-post']))
        self.assertEqual(post.slug, 'fresh-post')
        self.assertEqual(post.author, self.editor)

    def test_update_saves_changes(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse('posts-edit', args=['published-post']),
            self.post_data(title='Renamed', slug='published-post', summary='New blurb',
                           featured_image_url='https://example.com/a.png'))
        self.assertRedirects(response, reverse('posts-detail', args=['published-post']))
        self.published.refresh_from_db()
        self.assertEqual(self.published.title, 'Renamed')
        self.assertEqual(self.published.summary, 'New blurb')
        self.assertEqual(self.published.author, self.author)

    def test_delete_with_htmx_redirects_to_list(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse('posts-delete', args=['published-post']), HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Redirect'], reverse('posts-list'))
        self.assertFalse(Post.objects.filter(slug='published-post').exists())

    def test_delete_rejects_get(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse('posts-delete', args=['published-post']))
        self.assertEqual(response.status_code, 405)

    def test_preview_renders_markdown(self):
        self.client.force_login(self.editor)
        response = self.client.post(reverse('posts-preview'), {'markdown': '# Hello'})
        self.assertContains(response, '<h1 id="hello">Hello</h1>')

    def test_preview_of_blank_markdown_shows_placeholder(self):
        self.client.force_login(self.editor)
        response = self.client.post(reverse('posts-preview'), {'markdown': '  '})
        self.assertContains(response, 'Nothing to preview.')
