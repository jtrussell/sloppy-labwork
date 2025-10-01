
# Tourney

This app is dedicated to providing tournament software for KeyForge event
organizers (EOs) running tournaments at their local game stores and online.

The sweet spot for our tournaments will be in the 3-16 player count range.

Our guiding principle is to enable event organizers without overhead or
unnecessary guardrails. We understand that in most cases EOs will know their
players very well (high trust) and can shout across the room to sort out
issues. Local events should value relationships over rigid structure - as an
example, we prefer to allow late registrations and manual re-pairings over
forced structure.

## App Structure

Tourney specific static assets should live in `./static/tourney`:

```
./static/tourney/main.css # --> common tourney app styles
```

Specific pages and app-features can make single-purpose files, e.g.:

```
./static/tourney/drag-drop.css
./static/tourney/drag-drop.js
```

In addition, this app lives within the larger Sloppy Labwork project. Global
styles and other assets live here:

```
# Skeleton Framework
../static/css/vendor/skeleton-2.0.4/normalize.css
../static/css/vendor/skeleton-2.0.4/skeleton.css

# Base Project Styles
../static/css/main.css
```

We should always consider the appropriate level to introduce new styles and
scripts. In general, we should NOT include inline scripts and styles in our
templates.