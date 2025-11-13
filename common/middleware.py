
import json
from django.contrib.messages import get_messages
from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin


# From: https://github.com/bblanchon/django-htmx-messages-framework
class HtmxMessageMiddleware(MiddlewareMixin):
    """
    Middleware that moves messages into the HX-Trigger header when request is made with HTMX
    """

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        if "HX-Request" not in request.headers:
            return response
        if 300 <= response.status_code < 400:
            return response
        messages = [
            {"message": str(message.message), "tags": message.tags}
            for message in get_messages(request)
        ]
        if not messages:
            return response
        hx_trigger = response.headers.get("HX-Trigger")
        if hx_trigger is None:
            hx_trigger = {}
        elif hx_trigger.startswith("{"):
            hx_trigger = json.loads(hx_trigger)
        else:
            hx_trigger = {hx_trigger: True}
        hx_trigger["messages"] = messages
        response.headers["HX-Trigger"] = json.dumps(hx_trigger)
        return response
