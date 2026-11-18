from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Event, EventResult, Playgroup, PlaygroupEvent, PlaygroupMember

SIMPLE_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(STORAGES=SIMPLE_STORAGES)
class EventResultEditTests(TestCase):
    def setUp(self):
        self.playgroup = Playgroup.objects.create(name='Results Group', slug='results-group')
        self.organizer = self.create_member('Organizer', is_staff=True)
        self.player = self.create_member('Player')
        self.event = Event.objects.create(name='League Night', start_date=date.today())
        PlaygroupEvent.objects.create(playgroup=self.playgroup, event=self.event)
        self.result = EventResult.objects.create(
            event=self.event, user=self.player, finishing_position=2, num_wins=1, num_losses=2, num_ties=0)
        self.result_url = reverse('pmc-pg-manage-result', kwargs={'slug': self.playgroup.slug, 'pk': self.result.pk})

    def create_member(self, username, is_staff=False):
        user = User.objects.create_user(username=username)
        PlaygroupMember.objects.create(playgroup=self.playgroup, user=user, is_staff=is_staff)
        return user

    def post_edit(self, **overrides):
        data = {'finishing_position': '1', 'num_wins': '3', 'num_losses': '0', 'num_ties': ''}
        data.update(overrides)
        return self.client.post(self.result_url, data, HTTP_HX_REQUEST='true')

    def test_event_manage_page_offers_edit_and_confirmed_delete_for_each_result(self):
        self.client.force_login(self.organizer)
        response = self.client.get(
            reverse('pmc-pg-event-manage', kwargs={'slug': self.playgroup.slug, 'pk': self.event.pk}))
        self.assertContains(response, f'hx-get="{self.result_url}"')
        self.assertContains(response, f'hx-delete="{self.result_url}"')
        self.assertContains(response, 'hx-confirm="Delete the result for Player?')

    def test_staff_can_load_the_edit_form(self):
        self.client.force_login(self.organizer)
        response = self.client.get(self.result_url, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pmc/_event-result-edit-form.html')
        self.assertContains(response, 'id="dialog-title"')
        self.assertContains(response, f'hx-post="{self.result_url}"')
        self.assertContains(response, 'name="finishing_position" value="2"')
        self.assertContains(response, 'Player')

    def test_valid_edit_saves_and_returns_the_refreshed_table(self):
        self.client.force_login(self.organizer)
        response = self.post_edit()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('HX-Retarget', response.headers)
        self.assertContains(response, 'id="results-table"')
        self.assertContains(response, 'table__actions staff-only')
        self.result.refresh_from_db()
        self.assertEqual(self.result.finishing_position, 1)
        self.assertEqual(self.result.num_wins, 3)
        self.assertEqual(self.result.num_losses, 0)
        self.assertIsNone(self.result.num_ties)

    def test_invalid_edit_re_renders_errors_in_the_dialog(self):
        self.client.force_login(self.organizer)
        response = self.post_edit(num_wins='-4')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['HX-Retarget'], '#dialog')
        self.assertEqual(response.headers['HX-Reswap'], 'innerHTML')
        self.assertTemplateUsed(response, 'pmc/_event-result-edit-form.html')
        self.assertContains(response, 'field--invalid')
        self.assertContains(response, 'Ensure this value is greater than or equal to 0.')
        self.result.refresh_from_db()
        self.assertEqual(self.result.finishing_position, 2)
        self.assertEqual(self.result.num_wins, 1)

    def test_non_staff_member_cannot_load_the_edit_form(self):
        self.client.force_login(self.player)
        with self.assertLogs('django.request', level='WARNING'):
            response = self.client.get(self.result_url, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 403)

    def test_non_staff_member_cannot_submit_an_edit(self):
        self.client.force_login(self.player)
        with self.assertLogs('django.request', level='WARNING'):
            response = self.post_edit()
        self.assertEqual(response.status_code, 403)
        self.result.refresh_from_db()
        self.assertEqual(self.result.finishing_position, 2)


@override_settings(STORAGES=SIMPLE_STORAGES)
class EventResultOtherPlaygroupTests(TestCase):
    def setUp(self):
        home_playgroup = Playgroup.objects.create(name='Home Group', slug='home-group')
        other_playgroup = Playgroup.objects.create(name='Other Group', slug='other-group')
        player = User.objects.create_user(username='Player')
        PlaygroupMember.objects.create(playgroup=home_playgroup, user=player)
        other_organizer = User.objects.create_user(username='OtherOrganizer')
        PlaygroupMember.objects.create(playgroup=other_playgroup, user=other_organizer, is_staff=True)
        event = Event.objects.create(name='Home League Night', start_date=date.today())
        PlaygroupEvent.objects.create(playgroup=home_playgroup, event=event)
        self.result = EventResult.objects.create(
            event=event, user=player, finishing_position=2, num_wins=1, num_losses=2, num_ties=0)
        self.result_url_through_other_playgroup = reverse(
            'pmc-pg-manage-result', kwargs={'slug': other_playgroup.slug, 'pk': self.result.pk})
        self.client.force_login(other_organizer)

    def assert_not_found(self, response):
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, 'Player', status_code=404)

    def test_staff_of_another_playgroup_cannot_load_the_edit_form(self):
        with self.assertLogs('django.request', level='WARNING'):
            response = self.client.get(self.result_url_through_other_playgroup, HTTP_HX_REQUEST='true')
        self.assert_not_found(response)

    def test_staff_of_another_playgroup_cannot_edit_the_result(self):
        with self.assertLogs('django.request', level='WARNING'):
            response = self.client.post(
                self.result_url_through_other_playgroup,
                {'finishing_position': '1', 'num_wins': '3', 'num_losses': '0', 'num_ties': ''},
                HTTP_HX_REQUEST='true')
        self.assert_not_found(response)
        self.result.refresh_from_db()
        self.assertEqual(self.result.finishing_position, 2)

    def test_staff_of_another_playgroup_cannot_delete_the_result(self):
        with self.assertLogs('django.request', level='WARNING'):
            response = self.client.delete(self.result_url_through_other_playgroup, HTTP_HX_REQUEST='true')
        self.assert_not_found(response)
        self.assertTrue(EventResult.objects.filter(pk=self.result.pk).exists())


@override_settings(STORAGES=SIMPLE_STORAGES)
class EventBelongsToPlaygroupTests(TestCase):
    def setUp(self):
        self.home_playgroup = Playgroup.objects.create(name='Home Group', slug='home-group')
        self.other_playgroup = Playgroup.objects.create(name='Other Group', slug='other-group')
        self.player = User.objects.create_user(username='Player')
        PlaygroupMember.objects.create(playgroup=self.home_playgroup, user=self.player)
        self.other_organizer = User.objects.create_user(username='OtherOrganizer')
        PlaygroupMember.objects.create(playgroup=self.other_playgroup, user=self.other_organizer, is_staff=True)
        self.event = Event.objects.create(name='Home League Night', start_date=date.today())
        PlaygroupEvent.objects.create(playgroup=self.home_playgroup, event=self.event)
        self.result = EventResult.objects.create(
            event=self.event, user=self.player, finishing_position=2, num_wins=1, num_losses=2, num_ties=0)
        self.client.force_login(self.other_organizer)

    def event_url_through_other_playgroup(self, url_name):
        return reverse(url_name, kwargs={'slug': self.other_playgroup.slug, 'pk': self.event.pk})

    def assert_not_found(self, method, url, data=None):
        with self.assertLogs('django.request', level='WARNING'):
            response = getattr(self.client, method)(url, data or {})
        self.assertEqual(response.status_code, 404)

    def test_event_page_is_not_found_through_another_playgroup(self):
        self.assert_not_found('get', self.event_url_through_other_playgroup('pmc-pg-event-detail'))

    def test_event_cannot_be_managed_through_another_playgroup(self):
        self.assert_not_found('get', self.event_url_through_other_playgroup('pmc-pg-event-manage'))
        self.assert_not_found(
            'post', self.event_url_through_other_playgroup('pmc-pg-event-manage'), {'name': 'Renamed'})
        self.event.refresh_from_db()
        self.assertEqual(self.event.name, 'Home League Night')

    def test_event_cannot_be_deleted_through_another_playgroup(self):
        self.assert_not_found('post', self.event_url_through_other_playgroup('pmc-delete-event'))
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

    def test_points_cannot_be_reassigned_through_another_playgroup(self):
        self.assert_not_found('post', self.event_url_through_other_playgroup('pmc-event-assign-points'))

    def test_result_cannot_be_added_through_another_playgroup(self):
        self.assert_not_found(
            'post', self.event_url_through_other_playgroup('pmc-pg-add-event-result'),
            {'username': self.other_organizer.username})
        self.assertEqual(self.event.results.count(), 1)

    def test_player_cannot_be_checked_in_through_another_playgroup(self):
        self.assert_not_found(
            'post', self.event_url_through_other_playgroup('pmc-event-checkin'), {'qr_code_message': '{}'})
        self.assertEqual(self.event.results.count(), 1)

    def test_registration_cannot_be_toggled_through_another_playgroup(self):
        self.assert_not_found('post', self.event_url_through_other_playgroup('pmc-event-register'))
        self.assertEqual(self.event.results.count(), 1)

    def test_result_page_is_not_found_through_another_playgroup(self):
        self.assert_not_found('get', reverse(
            'pmc-result-detail', kwargs={'slug': self.other_playgroup.slug, 'pk': self.result.pk}))

    def test_staff_of_every_playgroup_sharing_an_event_can_manage_it(self):
        PlaygroupEvent.objects.create(playgroup=self.other_playgroup, event=self.event)
        response = self.client.get(self.event_url_through_other_playgroup('pmc-pg-event-manage'))
        self.assertEqual(response.status_code, 200)
