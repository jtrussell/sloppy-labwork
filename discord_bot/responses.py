RESPONSE_TYPE_PONG = 1
RESPONSE_TYPE_CHANNEL_MESSAGE = 4
RESPONSE_TYPE_DEFERRED_CHANNEL_MESSAGE = 5
RESPONSE_TYPE_UPDATE_MESSAGE = 7
RESPONSE_TYPE_AUTOCOMPLETE_RESULT = 8
RESPONSE_TYPE_MODAL = 9

MESSAGE_FLAG_EPHEMERAL = 1 << 6

COMPONENT_TYPE_ACTION_ROW = 1
COMPONENT_TYPE_BUTTON = 2
COMPONENT_TYPE_STRING_SELECT = 3
COMPONENT_TYPE_TEXT_INPUT = 4
COMPONENT_TYPE_LABEL = 18
COMPONENT_TYPE_RADIO_GROUP = 21
COMPONENT_TYPE_CHECKBOX = 23

BUTTON_STYLE_PRIMARY = 1
BUTTON_STYLE_LINK = 5

TEXT_INPUT_STYLE_SHORT = 1


def pong():
    return {'type': RESPONSE_TYPE_PONG}


def message(content):
    return {
        'type': RESPONSE_TYPE_CHANNEL_MESSAGE,
        'data': {'content': content},
    }


def ephemeral_message(content, components=None):
    data = {'content': content, 'flags': MESSAGE_FLAG_EPHEMERAL}
    if components:
        data['components'] = components
    return {'type': RESPONSE_TYPE_CHANNEL_MESSAGE, 'data': data}


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


def modal(custom_id, title, components):
    return {
        'type': RESPONSE_TYPE_MODAL,
        'data': {'custom_id': custom_id, 'title': title, 'components': components},
    }


def autocomplete_choices(choices):
    return {
        'type': RESPONSE_TYPE_AUTOCOMPLETE_RESULT,
        'data': {'choices': choices},
    }


def action_row(*components):
    return {'type': COMPONENT_TYPE_ACTION_ROW, 'components': list(components)}


def string_select(custom_id, options, placeholder=None, required=None):
    select = {
        'type': COMPONENT_TYPE_STRING_SELECT,
        'custom_id': custom_id,
        'options': options,
    }
    if placeholder:
        select['placeholder'] = placeholder
    if required is not None:
        select['required'] = required
        select['min_values'] = 1 if required else 0
    return select


def select_option(label, value, default=False):
    return {'label': label, 'value': value, 'default': default}


def button(custom_id, label, style=BUTTON_STYLE_PRIMARY):
    return {'type': COMPONENT_TYPE_BUTTON, 'custom_id': custom_id, 'label': label, 'style': style}


def link_button(url, label):
    return {'type': COMPONENT_TYPE_BUTTON, 'url': url, 'label': label, 'style': BUTTON_STYLE_LINK}


def label(text, component, description=None):
    wrapped = {'type': COMPONENT_TYPE_LABEL, 'label': text, 'component': component}
    if description:
        wrapped['description'] = description
    return wrapped


def text_input(custom_id, required=True, max_length=None, placeholder=None):
    component = {
        'type': COMPONENT_TYPE_TEXT_INPUT,
        'custom_id': custom_id,
        'style': TEXT_INPUT_STYLE_SHORT,
        'required': required,
    }
    if max_length:
        component['max_length'] = max_length
    if placeholder:
        component['placeholder'] = placeholder
    return component


def radio_group(custom_id, options, required=True):
    return {
        'type': COMPONENT_TYPE_RADIO_GROUP,
        'custom_id': custom_id,
        'options': options,
        'required': required,
    }


def radio_option(label_text, value):
    return {'label': label_text, 'value': value}


def checkbox(custom_id):
    return {'type': COMPONENT_TYPE_CHECKBOX, 'custom_id': custom_id}
