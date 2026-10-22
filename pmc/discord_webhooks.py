import logging
import re
import threading

import requests
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL_PATTERN = re.compile(
    r'^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api(?:/v\d+)?/webhooks/\d+/[\w-]+/?$')
DISCORD_MARKDOWN_CHARACTERS = re.compile(r'([\\*_~`|>])')
DISCORD_REQUEST_TIMEOUT_SECONDS = 3
DISCORD_USERNAME = 'KeyChain'
EMBED_TITLE_LIMIT = 256
EMBED_DESCRIPTION_LIMIT = 4096
EMBED_FIELD_VALUE_LIMIT = 1024
EMBED_FOOTER_LIMIT = 2048


def is_discord_webhook_url(url):
    return bool(DISCORD_WEBHOOK_URL_PATTERN.match(url or ''))


def validate_discord_webhook_url(url):
    if url and not is_discord_webhook_url(url):
        raise ValidationError(
            _('Enter a Discord webhook URL, e.g. https://discord.com/api/webhooks/123/abc.'))


def escape_markdown(text):
    return DISCORD_MARKDOWN_CHARACTERS.sub(r'\\\1', str(text))


def truncate(text, limit):
    text = str(text)
    return text if len(text) <= limit else f'{text[:limit - 1]}…'


def discord_timestamp(moment, style='R'):
    return f'<t:{int(moment.timestamp())}:{style}>'


def build_message(embed, mentioned_discord_ids=()):
    mention_ids = [str(discord_id) for discord_id in mentioned_discord_ids if discord_id]
    message = {
        'username': DISCORD_USERNAME,
        'embeds': [embed],
        'allowed_mentions': {'parse': [], 'users': mention_ids},
    }
    if mention_ids:
        message['content'] = ' '.join(f'<@{discord_id}>' for discord_id in mention_ids)
    return message


def post_message(webhook_url, message):
    if not is_discord_webhook_url(webhook_url):
        return False, _('This is not a Discord webhook URL.')
    try:
        response = requests.post(
            webhook_url, json=message, timeout=DISCORD_REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as error:
        logger.warning('Discord webhook request failed: %s', error)
        return False, _('Discord could not be reached.')
    except Exception:
        logger.exception('Unexpected error posting a Discord webhook')
        return False, _('Something went wrong sending the message.')
    if response.status_code >= 400:
        logger.warning('Discord webhook returned %s: %s', response.status_code, response.text[:500])
        return False, _('Discord rejected the message (HTTP %(status)s).') % {'status': response.status_code}
    return True, ''


def run_in_background(function, *args):
    threading.Thread(target=function, args=args, daemon=True).start()


def post_message_in_background(webhook_url, message):
    if webhook_url:
        run_in_background(post_message, webhook_url, message)
