INTERACTION_TYPE_PING = 1
INTERACTION_TYPE_APPLICATION_COMMAND = 2
INTERACTION_TYPE_MESSAGE_COMPONENT = 3
INTERACTION_TYPE_AUTOCOMPLETE = 4
INTERACTION_TYPE_MODAL_SUBMIT = 5


class Interaction:
    def __init__(self, payload):
        self.payload = payload

    @property
    def type(self):
        return self.payload['type']

    @property
    def data(self):
        return self.payload.get('data', {})

    @property
    def command_name(self):
        return self.data.get('name')

    @property
    def options(self):
        return self.data.get('options', [])

    def option(self, name, default=None):
        for option in self.options:
            if option['name'] == name:
                return option['value']
        return default

    @property
    def user(self):
        if 'member' in self.payload:
            return self.payload['member']['user']
        return self.payload['user']

    @property
    def user_id(self):
        return self.user['id']

    @property
    def guild_id(self):
        return self.payload.get('guild_id')

    @property
    def locale(self):
        return self.payload.get('locale')
