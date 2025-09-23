# Sloppy Labwork

This is a Python/Django project which contains code for two sites:

- "Sloppy Labwork" - A site dedicated to the (infamous?) KeyForge team, content,
  gizmos, etc.
- "KeyChain" - An app that allows KeyForge groups and their players record
  results from events and track their progress over time with leaderboards and
  award systems.

## The Golden Rule(s)

- Always confirm changes before applying them unless explicitly asked to skip confirmation.
- Treat `git` as read only. Never commit, push, rebase, etc. unless explicitly asked.,
- Prefer self-documenting code over comments. NEVER add comments to the code
unless asked to directly.
- Prefer using existing tools and dependencies, but do suggest when a popular
  3rd party solution exists and would offer a better solve.
- Favor existing styles and patterns, but do suggest alternatives -
  especially when a best practice is not being observed.

## Technology

- Python/Django - see `./requirements.txt` and `./.python-version` for a complete list of dependencies
- Deployment envionment: Heroku
- htmx


## App Structure

The `sloppy_labwork` folder contains code for the main app of the Sloppy Labwork site.

The `pmc` folder contains all code for the KeyChain app.

All other Django apps are either common to both projects or support the Sloppy
Labwork site exclusively. Both sites have their own dedicated page templates,
layouts, and stylesheets. They share an auth system and user base.

In typical Django fashion, within each Django app our code is split into files
by function:

- `admin.py` - Models and custom functionality related to the Django admin area
- `forms.py` - While we do have some SPA like behavior, we try to lean toward
  SSR style pages with forms to drive data changes.
- `models.py` - The model definitions for each app, we prefer to keep most
- `management/commands.py` - Custom Django commands get registered here. This is
  useful for setup and maintenance scripts that need to be run manually.
  business logic close to the models themselves.
- `views.py` - Our controllers/route handlers.
- `templates/` - Page templates

All stylesheets are centralized at the root of the repo in `./static/css` with
KeyChain related stylesheets in `./static/pmc/css` Note that we have a
`main.css` stylesheet containing global stiles for both sites as well as page
specific stylesheets.

## Agents

Please coordinate with the following agents to plan tasks:

- `ui-researcher` - Coordinate with this agent to when planning a UI intensive task.
- `django-expert` - This agent should be consulted on most tasks, any that interact with the Django framework.
- `htmx-expert` - Consult this agent when using htmx or when asked to add SPA-like behavior to our experiences.

Use the folder `.claude/.local/agent-artifacts` as a context cache and to share
artifacts with your agents. Please create this folder if it doesn't exist.