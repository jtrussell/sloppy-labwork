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
    def __init__(self, definition, handler, autocomplete=None, component=None, modal=None, help_text=None):
        self.definition = definition
        self.handler = handler
        self.autocomplete = autocomplete
        self.component = component
        self.modal = modal
        self.help_text = help_text

    @property
    def name(self):
        return self.definition['name']

    @property
    def description(self):
        return self.definition['description']


def get_commands():
    from .commands import help as help_command, lineup, random_access_archives, tourney
    return [
        help_command.command,
        lineup.command,
        random_access_archives.command,
        tourney.command,
    ]


def get_command(name):
    for command in get_commands():
        if command.name == name:
            return command
    return None
