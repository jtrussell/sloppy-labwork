---
name: add-feature
description: Plan, build and verify a new feature for the Sloppy Labwork site. Use when asked to add or extend a feature on Sloppy Labwork.
---

# Add a Sloppy Labwork feature

## Before planning

- If the feature is user facing, review the design system first: the
  "Design System (Sloppy Labwork)" section of `CLAUDE.md`, the Principles in
  `design_system/templates/design_system/index.html`, and the gallery sections
  relevant to the feature (`/design-system/`).
- Review the existing tests for the apps the feature touches.

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

## While building

- Python code is PEP 8 formatted. Run `uv run autopep8 --in-place <files>` on
  every Python file the feature touched, and only those files. Settings live
  under `[tool.autopep8]` in `pyproject.toml`.
- User-facing work follows the design system as a first principle: existing
  tokens, components and includes before anything new.

## Verifying

- Run the tests named in the plan and report the real result.
- Where the feature has UI, review it in the browser and compare it against
  the design system gallery, in all four themes and at phone width.
- If the design system falls short, propose a change to it instead of working
  around it in the feature. Wait for approval before changing it.
