from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


ADMIN_SEARCH_TERM = 'someone'


def get_searchable_model_admins():
    return [
        model_admin for model_admin in admin.site._registry.values()
        if model_admin.search_fields
    ]


def get_changelist_url(model_admin):
    model_options = model_admin.model._meta
    return reverse(f'admin:{model_options.app_label}_{model_options.model_name}_changelist')


class AdminSearchTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='admin-searcher', email='admin-searcher@example.com', password='password')

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_every_searchable_admin_handles_a_search(self):
        for model_admin in get_searchable_model_admins():
            with self.subTest(model_admin=type(model_admin).__name__):
                response = self.client.get(get_changelist_url(model_admin), {'q': ADMIN_SEARCH_TERM})

                self.assertEqual(response.status_code, 200)
