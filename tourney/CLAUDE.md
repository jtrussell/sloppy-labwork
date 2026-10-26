
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

In addition, this app lives within the larger Sloppy Labwork project and uses
its design system. See "Design System (Sloppy Labwork)" in the root
`CLAUDE.md` for the stylesheet layers, rules, includes and scripts, and browse
`/design-system/` for live examples before building tourney UI.

Tourney pages render inside `page.html` (KeyChain's host doesn't route
tourney URLs), so global components, tokens and includes are always
available here.

We should always consider the appropriate level to introduce new styles and
scripts: reusable UI belongs in the design system, tourney-specific styles in
`./static/tourney/`. In general, we should NOT include inline scripts and
styles in our templates.