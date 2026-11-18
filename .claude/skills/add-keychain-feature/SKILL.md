---
name: add-keychain-feature
description: Plan, build and verify a new feature for KeyChain (the pmc app). Use when asked to add or extend a feature on KeyChain.
---

# Add a KeyChain feature

## Before planning

- If the feature is user facing, review the KeyChain design system first: the
  "Design System" section of `pmc/CLAUDE.md`, the Principles in
  `pmc/templates/pmc/ds-index.html`, and the gallery sections relevant to the
  feature (`/design-system/` on the KeyChain host, `/pmc/design-system/` on
  the main host).
- Review the existing tests for the area the feature touches (`pmc/tests*.py`).
- Decide who the feature is for: every player, playgroup members, or playgroup
  staff. Staff features carry the staff look and are protected on the server.

## The plan must include

- How we will verify the feature works: which tests are added or changed and
  the command that runs them, plus what will be checked in the browser.
- Any schema changes, expressed as model changes. We are code-first and lean
  on the Django ORM: change the models, then generate the migration with
  `uv run python manage.py makemigrations`. Never hand-write SQL or schema
  migrations.
- Never run `migrate` against the user's development database or any shared
  database without explicit permission. A throwaway database or container
  may be created and migrated freely for development and testing.
- For staff features: where the server refuses non-staff. Hiding a control
  with `.staff-only` is fine; data and capabilities are withheld in the view
  or the template with `playgroup_member.is_staff`.

## While building

- Keep `pmc` self-contained: templates in `pmc/templates/pmc/`, assets in
  `static/pmc/`, nothing imported from the Sloppy Labwork design system.
- Python code is PEP 8 formatted. Run `uv run autopep8 --in-place <files>` on
  every Python file the feature touched, and only those files.
- User-facing work follows the design system as a first principle: existing
  tokens, components and includes before anything new. Phone layout first.
- Text shown through `hx-confirm` or Django messages may contain names typed
  by users: confirms are plain text, and messages with markup use
  `format_html`. User-written markdown goes through `markdown_sanitized`.
- Wording about playgroup activity is positive only; quiet playgroups get
  neutral facts.

## Verifying

- Run the tests named in the plan and report the real result.
  `uv run python manage.py test pmc` runs every KeyChain test.
- Where the feature has UI, review it in the browser against a throwaway
  copy of the database, and compare it with the design system gallery, in
  both themes and at phone width (the tab bar must not cover the last
  control on the page).
- If the design system falls short, propose a change to it instead of working
  around it in the feature. Wait for approval before changing it.
