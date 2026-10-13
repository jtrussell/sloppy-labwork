from .registry import OPTION_TYPE_SUB_COMMAND, OPTION_TYPE_SUB_COMMAND_GROUP

INTERACTION_TYPE_PING = 1
INTERACTION_TYPE_APPLICATION_COMMAND = 2
INTERACTION_TYPE_MESSAGE_COMPONENT = 3
INTERACTION_TYPE_AUTOCOMPLETE = 4
INTERACTION_TYPE_MODAL_SUBMIT = 5

CUSTOM_ID_SEPARATOR = ':'

SUBCOMMAND_OPTION_TYPES = (OPTION_TYPE_SUB_COMMAND, OPTION_TYPE_SUB_COMMAND_GROUP)


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
        if self.type == INTERACTION_TYPE_MESSAGE_COMPONENT:
            return self.custom_id.split(CUSTOM_ID_SEPARATOR)[0]
        return self.data.get('name')

    def walk_subcommands(self):
        subcommand_name = None
        options = self.data.get('options', [])
        while options and options[0].get('type') in SUBCOMMAND_OPTION_TYPES:
            subcommand_name = options[0]['name']
            options = options[0].get('options', [])
        return subcommand_name, options

    @property
    def subcommand_name(self):
        subcommand_name, _ = self.walk_subcommands()
        return subcommand_name

    @property
    def options(self):
        _, options = self.walk_subcommands()
        return options

    def option(self, name, default=None):
        for option in self.options:
            if option['name'] == name:
                return option['value']
        return default

    @property
    def focused_option(self):
        for option in self.options:
            if option.get('focused'):
                return option
        return None

    @property
    def custom_id(self):
        return self.data.get('custom_id', '')

    @property
    def selected_values(self):
        return self.data.get('values', [])

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
