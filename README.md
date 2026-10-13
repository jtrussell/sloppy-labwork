# Sloppy Labwork

[![PEP8](https://img.shields.io/badge/code%20style-pep8-orange.svg)](https://www.python.org/dev/peps/pep-0008/)

## Setup

### Docker

You want to work with Docker? Nice! You can skip all the Python setup steps
below. We just have to make sure our local configuration files get created.
Git ignores this file (it contains secrets), but we do keep a handy template
around that will get you off the ground:

```
cp ./sloppy_labwork/local_environment.py-example ./sloppy_labwork/local_environment.py
```

### Local Development with uv

We use [uv](https://docs.astral.sh/uv/) for package and environment management.
The Python version is specified in `.python-version`.

1. Install uv if you haven't already:
   ```
   # macOS/Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Windows
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. Sync dependencies (this creates the virtual environment automatically):
   ```
   uv sync
   ```

3. Copy the local environment template:
   ```
   cp ./sloppy_labwork/local_environment.py-example ./sloppy_labwork/local_environment.py
   ```

You may update this local environment file to turn features on/off and update app secrets.


## Run It

### Docker

Start the app with:

```
docker-compose up
```

And you should be good to go!

Note that the first time you run the app, as well as any time you wish to
apply database migrations, you'll have to do so with the following command:

```
docker-compose exec web python manage.py migrate
```

### Local Development

Once setup is complete, you can apply database migrations with:

```
uv run python manage.py migrate
```

And run the development server with:

```
uv run python manage.py runserver
```


## Signing In

In production, we only support signing in via 3rd party authentication
providers. The most convenient way to authenticate during development is by
using the Django Admin at
[http://localhost:8000/admin](http://localhost:8000/admin).

Alternatively, you may enter a `SocialApp` record in the DB for your own
Discord app.


## Discord Bot

The Sloppy Labwork Discord bot lives in the `discord_bot` app. It is an
interactions-endpoint bot: Discord POSTs slash command invocations to
`discord/interactions/`, where `discord_bot/views.py` verifies the signature
and dispatches to the command's handler. Each command is one module under
`discord_bot/commands/` exposing its Discord definition and a handler, and is
listed in `discord_bot/registry.py`. Commands may also provide autocomplete,
component, and modal submit handlers; component and modal `custom_id`s are
prefixed with the command name (e.g. `lineup:version`) so they route back to
their command. Commands must be (re)registered with
Discord any time a definition changes.

Registration is done with a management command. It needs `DISCORD_APP_ID` and
`DISCORD_BOT_TOKEN` in the environment (see the local environment example)
and overwrites the full set of commands, so removed commands are deleted too.

```
uv run python manage.py register_discord_commands --dry-run
uv run python manage.py register_discord_commands --guild <guild id>
uv run python manage.py register_discord_commands
```

Guild-scoped registration is instant and good for testing in one server.
Global registration can take up to an hour to propagate. A server that has
guild-scoped commands registered will show both the guild and global copies of
each command until the guild set is cleared.

In production, run the "Register Discord Commands" workflow from the GitHub
Actions tab. It reads `DISCORD_APP_ID` and `DISCORD_BOT_TOKEN` from the
repository's Actions secrets and accepts an optional guild id input.
