
# KeyChain

This folder contains the KeyChain app, it is largely treated as a separate site
entirely from the remainder of the project though does not make use of Django's
"sites" capabilities.

Stylesheets are stored in `/static/pmc/css` with `/static/pmc/css/main.css`
providing global styles for the site and other files in that folder containing
page-specific styles.

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