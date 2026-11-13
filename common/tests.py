import json

from django.contrib import messages
from django.contrib.messages.storage.cookie import CookieStorage
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.utils.html import format_html

from .middleware import HtmxMessageMiddleware


class HtmxMessageMiddlewareTests(SimpleTestCase):
    def _get_triggered_messages(self, add_messages, **request_headers):
        request = RequestFactory().get('/', **request_headers)
        request._messages = CookieStorage(request)
        add_messages(request)
        middleware = HtmxMessageMiddleware(lambda request: HttpResponse())
        response = middleware.process_response(request, HttpResponse())
        return json.loads(response.headers.get('HX-Trigger', '{}')).get('messages')

    def test_plain_message_text_is_escaped(self):
        triggered_messages = self._get_triggered_messages(
            lambda request: messages.success(request, 'Lineup "<img src=x onerror=alert(1)>" created!'),
            HTTP_HX_REQUEST='true')

        self.assertEqual(triggered_messages, [{
            'message': 'Lineup &quot;&lt;img src=x onerror=alert(1)&gt;&quot; created!',
            'tags': 'success',
        }])

    def test_safe_message_markup_is_kept(self):
        triggered_messages = self._get_triggered_messages(
            lambda request: messages.error(request, format_html('<a href="/help/">{}</a>', '<Help>')),
            HTTP_HX_REQUEST='true')

        self.assertEqual(triggered_messages, [{
            'message': '<a href="/help/">&lt;Help&gt;</a>',
            'tags': 'error',
        }])

    def test_messages_stay_put_without_htmx(self):
        triggered_messages = self._get_triggered_messages(
            lambda request: messages.success(request, 'Saved.'))

        self.assertIsNone(triggered_messages)
