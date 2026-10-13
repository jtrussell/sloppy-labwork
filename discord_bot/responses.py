RESPONSE_TYPE_PONG = 1
RESPONSE_TYPE_CHANNEL_MESSAGE = 4
RESPONSE_TYPE_DEFERRED_CHANNEL_MESSAGE = 5
RESPONSE_TYPE_UPDATE_MESSAGE = 7
RESPONSE_TYPE_AUTOCOMPLETE_RESULT = 8

MESSAGE_FLAG_EPHEMERAL = 1 << 6

COMPONENT_TYPE_ACTION_ROW = 1
COMPONENT_TYPE_STRING_SELECT = 3


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


def embed_message(embeds, components=None, ephemeral=False):
    data = {'embeds': embeds, 'components': components or []}
    if ephemeral:
        data['flags'] = MESSAGE_FLAG_EPHEMERAL
    return {'type': RESPONSE_TYPE_CHANNEL_MESSAGE, 'data': data}


def update_message(embeds, components=None):
    return {
        'type': RESPONSE_TYPE_UPDATE_MESSAGE,
        'data': {'embeds': embeds, 'components': components or []},
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


def action_row(*components):
    return {'type': COMPONENT_TYPE_ACTION_ROW, 'components': list(components)}


def string_select(custom_id, options, placeholder=None):
    select = {
        'type': COMPONENT_TYPE_STRING_SELECT,
        'custom_id': custom_id,
        'options': options,
    }
    if placeholder:
        select['placeholder'] = placeholder
    return select


def select_option(label, value, default=False):
    return {'label': label, 'value': value, 'default': default}
