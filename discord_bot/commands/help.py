from ..registry import (
    Command,
    COMMAND_TYPE_CHAT_INPUT,
    OPTION_TYPE_SUB_COMMAND,
    OPTION_TYPE_SUB_COMMAND_GROUP,
    OPTION_TYPE_STRING,
    OPTION_TYPE_INTEGER,
    OPTION_TYPE_BOOLEAN,
    OPTION_TYPE_USER,
    choice,
    get_command,
    get_commands,
)
from ..responses import embed_message, ephemeral_message, autocomplete_choices
from ..text import truncate

COMMAND_NAME = 'help'
OPTION_COMMAND = 'command'

MAX_CHOICES = 25
MAX_EMBED_DESCRIPTION_LENGTH = 4096

SUBCOMMAND_OPTION_TYPES = (OPTION_TYPE_SUB_COMMAND, OPTION_TYPE_SUB_COMMAND_GROUP)

VALUE_PLACEHOLDER_BY_OPTION_TYPE = {
    OPTION_TYPE_STRING: 'text',
    OPTION_TYPE_INTEGER: 'number',
    OPTION_TYPE_BOOLEAN: 'true/false',
    OPTION_TYPE_USER: 'user',
}

OVERVIEW_TITLE = 'Sloppy Labwork bot commands'
OVERVIEW_FOOTER = 'Use /help command:<name> to see how a command works.'

definition = {
    'name': COMMAND_NAME,
    'type': COMMAND_TYPE_CHAT_INPUT,
    'description': 'List the bot\'s commands or show how one works',
    'options': [
        {
            'name': OPTION_COMMAND,
            'description': 'Command to show usage for',
            'type': OPTION_TYPE_STRING,
            'required': False,
            'autocomplete': True,
        },
    ],
}


def unknown_command_message(command_name):
    return f'I don\'t know a command called `{command_name}`. Use `/help` to see them all.'


def describe_option_usage(option):
    placeholder = VALUE_PLACEHOLDER_BY_OPTION_TYPE.get(option['type'], 'value')
    usage = f'{option["name"]}:<{placeholder}>'
    return usage if option.get('required') else f'[{usage}]'


def describe_option(option):
    optional_marker = '' if option.get('required') else ' (optional)'
    line = f'• `{option["name"]}`{optional_marker} — {option["description"]}'
    choices = option.get('choices')
    if choices:
        line += '. One of: ' + ', '.join(choice['name'] for choice in choices)
    return line


def describe_invocation(command_path, options, description=None):
    usage = ' '.join([f'/{command_path}'] + [describe_option_usage(option) for option in options])
    lines = [f'`{usage}`']
    if description:
        lines.append(description)
    lines.extend(describe_option(option) for option in options)
    return '\n'.join(lines)


def describe_invocations(command_path, options, description=None):
    subcommands = [option for option in options if option['type'] in SUBCOMMAND_OPTION_TYPES]
    if not subcommands:
        return [describe_invocation(command_path, options, description)]
    invocations = []
    for subcommand in subcommands:
        invocations.extend(describe_invocations(
            f'{command_path} {subcommand["name"]}',
            subcommand.get('options', []),
            subcommand['description'],
        ))
    return invocations


def build_command_usage_embed(command):
    sections = [command.description]
    if command.help_text:
        sections.append(command.help_text)
    sections.extend(describe_invocations(command.name, command.definition.get('options', [])))
    return {
        'title': f'/{command.name}',
        'description': truncate('\n\n'.join(sections), MAX_EMBED_DESCRIPTION_LENGTH),
    }


def build_overview_embed():
    lines = [f'`/{command.name}` — {command.description}' for command in get_commands()]
    return {
        'title': OVERVIEW_TITLE,
        'description': truncate('\n'.join(lines), MAX_EMBED_DESCRIPTION_LENGTH),
        'footer': {'text': OVERVIEW_FOOTER},
    }


def handle(interaction):
    command_name = interaction.option(OPTION_COMMAND)
    if not command_name:
        return embed_message([build_overview_embed()], ephemeral=True)
    command = get_command(command_name.strip().lstrip('/').lower())
    if command is None:
        return ephemeral_message(unknown_command_message(command_name))
    return embed_message([build_command_usage_embed(command)], ephemeral=True)


def autocomplete(interaction):
    query = (interaction.focused_option or {}).get('value', '').strip().lstrip('/').lower()
    command_names = [command.name for command in get_commands() if query in command.name]
    return autocomplete_choices([choice(name, name) for name in command_names[:MAX_CHOICES]])


command = Command(definition, handle, autocomplete=autocomplete)
