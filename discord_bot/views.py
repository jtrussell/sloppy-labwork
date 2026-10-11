import json
import logging
import os
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from .interactions import Interaction, INTERACTION_TYPE_PING, INTERACTION_TYPE_APPLICATION_COMMAND
from .registry import get_command
from .responses import pong, ephemeral_message

logger = logging.getLogger(__name__)

UNKNOWN_COMMAND_MESSAGE = 'I don\'t know that command. It may have been removed or not registered yet.'
UNSUPPORTED_INTERACTION_MESSAGE = 'I can\'t handle that kind of interaction yet.'
COMMAND_FAILED_MESSAGE = 'Oops! Something went wrong running that command.'


def has_valid_signature(request):
    signature = request.headers.get('X-Signature-Ed25519')
    timestamp = request.headers.get('X-Signature-Timestamp')
    if not signature or not timestamp:
        return False
    verify_key = VerifyKey(bytes.fromhex(os.environ['DISCORD_BOT_PUBLIC_KEY']))
    try:
        verify_key.verify(timestamp.encode() + request.body, bytes.fromhex(signature))
    except (BadSignatureError, ValueError):
        return False
    return True


def dispatch(interaction):
    if interaction.type == INTERACTION_TYPE_PING:
        return pong()
    if interaction.type != INTERACTION_TYPE_APPLICATION_COMMAND:
        logger.warning('Unsupported Discord interaction type %s', interaction.type)
        return ephemeral_message(UNSUPPORTED_INTERACTION_MESSAGE)
    command = get_command(interaction.command_name)
    if command is None:
        logger.warning('Unknown Discord command %s', interaction.command_name)
        return ephemeral_message(UNKNOWN_COMMAND_MESSAGE)
    try:
        return command.handler(interaction)
    except Exception:
        logger.exception('Discord command %s failed', interaction.command_name)
        return ephemeral_message(COMMAND_FAILED_MESSAGE)


@csrf_exempt
@require_POST
def interactions(request):
    if not has_valid_signature(request):
        return HttpResponse('Unauthorized', status=401)
    interaction = Interaction(json.loads(request.body))
    return JsonResponse(dispatch(interaction))
