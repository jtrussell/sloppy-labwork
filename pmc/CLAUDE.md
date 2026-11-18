
# KeyChain

This folder contains the KeyChain app, it is largely treated as a separate site
entirely from the remainder of the project though does not make use of Django's
"sites" capabilities.

Stylesheets are stored in `/static/pmc/css`. Every page loads one entry point,
`/static/pmc/css/keychain.css` (see Design System below); other files in that
folder hold page-specific styles.

I've been attempting to keep this app self-contained - making it easier to lift
to a dedicated Django project at some point in the future. That said, feel free
to suggest opportunities for separating functionality in smaller Django apps.

## Important Files

These follow Django conventions, consistent with what's described in the root `CLAUDE.md`


## KeyChain Conventions

- Templates with an `_` prefix are meant to be included by other templates and
  typically will not be rendered by themselves.
- Templates with a `g-` prefix are considered "global" for logged in users. This
  means they are accessible outside the context of a playgroup.
- Templates with a `pg-` prefix assume they are being viewed within the context
  of a playgroup.
 - Other templates (neither prefix), are accessible to
  unauthenticated users. This means there will not be a "user" or "playgroup" to
  reference reliably.
- Templates with a `ds-` prefix are design system gallery pages.

## Design System

KeyChain pages are built from the KeyChain design system. It lives entirely
inside `pmc` and is separate from the Sloppy Labwork design system.

- Gallery: `/design-system/` on the KeyChain host (`/pmc/design-system/` on the
  main host), Django staff only. It documents every token, component, include
  and page pattern in both themes. Source: `pmc/design_system.py` and the
  `ds-*.html` templates.
- Tests: `uv run python manage.py test pmc.tests_design_system` (every theme
  defines the same themeable tokens; no raw colours in any KeyChain
  stylesheet).
- Feature work: use the `add-keychain-feature` skill.

### Stylesheets

| Layer | File | Contents |
| --- | --- | --- |
| `reset` | `css/system/reset.css` | Normalisation |
| unlayered | `css/system/tokens.css` | Tokens for both themes |
| `base` | `css/system/base.css` | Element defaults, form controls, focus |
| `components` | `css/system/components.css` | Shell, layout primitives, components |
| `utilities` | `css/system/utilities.css` | Single-purpose helpers, staff hiding |

Page stylesheets and Leaflet are unlayered, so they win over the layers
without `!important`. Themes are `data-theme="0"` (dark) and `"1"` (light) on
`<html>`, matching `PmcProfile.theme`.

### Rules

1. Tokens for every colour, space, font size, radius and shadow. No hex, rgb
   or named colours outside `tokens.css`.
2. A new themeable token is defined in both theme blocks.
3. Reach for an existing component or include before writing CSS. If
   something reusable is missing, add it to the system and to the gallery.
4. Page stylesheets hold only what is specific to one feature.
5. Components have no outer margin. `.page`, `.card` and `.stack` space their
   children; use `.cluster`, `.grid` and `.split` for rows and columns.
6. Phone first: `min-width` media queries at 480px and 720px.
7. Interactive targets are at least 44px. Never remove focus outlines.
8. One `.btn--solid` per view for the main action. Groups of buttons go in an
   action row (`.card__actions` in a card, `.form__actions`, `.dialog__footer`,
   `.btn-row` in the page) with the main action last in the markup; the row
   handles phone and wide layouts itself.
9. Staff UI is marked with the blue staff accent and the word "Staff"
   (`.card--staff` with `.staff-tag`, `.btn--staff`, `.staff-link`), and pages
   only staff can open show the staff strip. `.staff-only` hides controls
   from non-staff with CSS; data and capabilities are withheld on the server.
10. Same-page reloads (filters, tabs, pagination, toggles) keep the scroll
    position with `data-preserve-scroll`.
11. Check new or changed UI in both themes and at phone width.

### Includes

In `pmc/templates/pmc/`: `_form-fields.html` and `_field.html` (replace
`form.as_p`), `_pagination.html`, `_empty.html`, `_icon.html` (sprite in
`_icon-sprite.html`), `_dialog-header.html`, `_dialog-host.html`,
`_dialog-confirm.html`, `_messages.html` / `_message.html`, `_staff-strip.html`,
`_nav.html`.

### JavaScript

In `static/pmc/scripts/`, loaded by the base template:

- `dialog.js` - native `<dialog class="dialog">`: `data-dialog-open`,
  `data-dialog-close`, the htmx dialog host (`#dialog`), and `hx-confirm`
  through the confirm dialog (plain text only).
- `messages.js` - Django messages fixed to the top of the viewport, including
  messages delivered by htmx responses (`HX-Trigger`).
- `menu.js` - `details[data-menu]`: action menus and the tab bar "More".
- `preserve-scroll.js` - `data-preserve-scroll`.

Loaded by the pages that need them:

- `qrcode-form.js` - QR scanning into a form. Expects `#qr-reader` (where the
  scanner renders), `#qr-code-message` (the input, usually hidden, that
  receives the scanned message), `#qr-btn-start` and `#qr-btn-stop`. Load the
  html5-qrcode library before it.

### Navigation

The primary navigation is a floating tab bar on phones and a link row from
720px. It shows `nav_links` (`pmc/context_processors.py`) in the order given;
each link names an `icon`. With more than five links, phones show the first
four and put the rest behind "More".
