# Sloppy Labwork

This is a Python/Django project which contains code for two sites:

- "Sloppy Labwork" - A site dedicated to the (infamous?) KeyForge team, content,
  gizmos, etc.
- "KeyChain" - An app that allows KeyForge groups and their players record
  results from events and track their progress over time with leaderboards and
  award systems.

## The Golden Rule(s)

- Always confirm changes before applying them unless explicitly asked to skip confirmation.
- Treat `git` as read only. Never commit, push, rebase, etc. unless explicitly asked.
- Prefer self-documenting code over comments. Do not add comments to the code.
- Favor consistency. Be reluctant to introduce new styles, patterns, or
  dependencies without asking first.

## Technology

- Python/Django - see `./pyproject.toml` and `./.python-version` for dependencies
- [uv](https://docs.astral.sh/uv/) - package and environment management
- Deployment environment: Heroku
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

Static assets are centralized at the root of the repo in `./static`. Global
Sloppy Labwork stylesheets live in `./static/css` (see Design System below).
KeyChain assets live in `./static/pmc`. Each gizmo or app keeps its own assets
in `./static/<app_name>/` (e.g. `./static/ghostform/main.css` and its
JavaScript files).

## Design System (Sloppy Labwork)

Sloppy Labwork pages are built from a shared design system. KeyChain (`pmc`)
does not use it and must not be affected by changes to it.

- Gallery: `/design-system/` (teammates and superusers). It documents every
  token, component, include and page pattern with live examples in all four
  themes. Source: the `design_system` app.
- Tests: `uv run python manage.py test design_system` (includes a check that
  every theme defines the complete set of themeable tokens).

### Stylesheets

Pages load one entry point, `static/css/site.css`, which assigns global
stylesheets to cascade layers:

| Layer | File | Contents |
| --- | --- | --- |
| `reset` | `css/vendor/skeleton-2.0.4/normalize.css` | Normalization |
| unlayered | `css/fonts.css`, `css/tokens.css` | Fonts, design tokens and themes |
| `base` | `css/base.css` | Element defaults and typography |
| `components` | `css/components.css` | Layout primitives and components |
| `utilities` | `css/utilities.css` | Single-purpose helpers |

App stylesheets (`static/<app>/main.css`) and template `<style>` blocks are
unlayered, so they always win over the layers without `!important` or
selector stacking.

### Rules

1. Use tokens from `tokens.css` for every color, space, font size, radius,
   shadow and transition. No hex, rgb or named colors outside `tokens.css`.
2. Use semantic tokens (`--color-danger`, `--color-surface`). The old aliases
   (`--color-lines`, `--color-bg-secondary`, ...) are gone; a `design_system`
   test fails if they or raw colors appear in a Sloppy Labwork stylesheet.
3. Tints come from `color-mix()` on a semantic token or `currentColor` with
   `--tint-subtle` / `--tint-strong`.
4. Reach for an existing component or include before writing new CSS. Check
   the gallery first. If something reusable is missing, add it to the system
   (CSS in `components.css`, include in `design_system/templates/components/`,
   and a gallery entry) rather than to an app stylesheet.
5. App stylesheets hold only what is specific to that app.
6. Components have no outer margin. Parents space children with `gap` via the
   layout primitives (stack, cluster, grid). Spacing values come from the
   `--space-*` scale.
7. Write mobile-first `min-width` media queries at the shared breakpoints:
   400px, 550px, 750px.
8. A new theme or token must be defined in every theme block of `tokens.css`.
9. Check new or changed UI in all four themes and at phone width. The gallery
   theme switcher and themed examples make this quick.
10. Don't remove focus outlines; keyboard focus is visible by design.

### Includes

In `design_system/templates/components/`:

- `field.html` / `form-fields.html` - Django form fields with label, required
  marker, help text and errors (keeps Django's ARIA wiring).
- `pagination.html`, `empty-state.html`, `table-empty-row.html`
- `messages.html` - Django messages as notes.
- `icon-sprite.html` (once per page) and `icon.html`
- `step-rail.html`
- `dialog-header.html`, `dialog-confirm.html`, `dialog-host.html`

### JavaScript

- `static/js/dialog.js` - native `<dialog>` behaviour: `data-dialog-open`,
  `data-dialog-close`, the htmx dialog host (`#dialog`) and `hx-confirm`
  through the confirm dialog.
- `static/js/copy.js` - `data-copy-text`, `data-copy-from` and
  `data-share-url` buttons.
- `static/js/action-menu.js` - closing behaviour for `details.action-menu`
  (outside press, item chosen, Escape). Use an action menu for 3+ actions or
  actions beside a title that can grow.

### Legacy

These predate the design system; don't use them in new code: `.hstack`,
`.gap-1` / `.gap-2` (use the stack and cluster modifiers), `.note-danger` (use
`.note--danger`), and `static/css/drag-drop.css` (KeyChain only, leave it
untouched).

## Agents

Please coordinate with the following agents to plan tasks:

- `ui-researcher` - Coordinate with this agent when planning a UI intensive task.
- `django-expert` - This agent should be consulted on most tasks, any that
  interact with the Django framework.
- `htmx-expert` - Consult this agent when using htmx or when asked to add
  SPA-like behavior to our experiences.

Use the folder `.claude/.local/agent-artifacts` as a context cache and to share
artifacts with your agents. Please create this folder if it doesn't exist.
