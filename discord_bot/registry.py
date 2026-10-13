COMMAND_TYPE_CHAT_INPUT = 1

OPTION_TYPE_SUB_COMMAND = 1
OPTION_TYPE_SUB_COMMAND_GROUP = 2
OPTION_TYPE_STRING = 3
OPTION_TYPE_INTEGER = 4
OPTION_TYPE_BOOLEAN = 5
OPTION_TYPE_USER = 6


def choice(name, value):
    return {'name': name, 'value': value}


class Command:
    def __init__(self, definition, handler, autocomplete=None, component=None):
        self.definition = definition
        self.handler = handler
        self.autocomplete = autocomplete
        self.component = component

    @property
    def name(self):
        return self.definition['name']


def get_commands():
    from .commands import lineup, random_access_archives
    return [
        random_access_archives.command,
        lineup.command,
    ]


def get_command(name):
    for command in get_commands():
        if command.name == name:
            return command
    return None
