RESPONSE_TYPE_PONG = 1
RESPONSE_TYPE_CHANNEL_MESSAGE = 4
RESPONSE_TYPE_DEFERRED_CHANNEL_MESSAGE = 5
RESPONSE_TYPE_AUTOCOMPLETE_RESULT = 8

MESSAGE_FLAG_EPHEMERAL = 1 << 6


def pong():
    return {'type': RESPONSE_TYPE_PONG}


def message(content):
    return {
        'type': RESPONSE_TYPE_CHANNEL_MESSAGE,
        'data': {'content': content},
    }


def ephemeral_message(content):
    return {
        'type': RESPONSE_TYPE_CHANNEL_MESSAGE,
        'data': {'content': content, 'flags': MESSAGE_FLAG_EPHEMERAL},
    }


def deferred_message(ephemeral=False):
    response = {'type': RESPONSE_TYPE_DEFERRED_CHANNEL_MESSAGE}
    if ephemeral:
        response['data'] = {'flags': MESSAGE_FLAG_EPHEMERAL}
    return response


def autocomplete_choices(choices):
    return {
        'type': RESPONSE_TYPE_AUTOCOMPLETE_RESULT,
        'data': {'choices': choices},
    }
