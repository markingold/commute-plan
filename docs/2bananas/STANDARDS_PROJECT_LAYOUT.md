<!--
id: STD-PROJECT-LAYOUT
version: 1.2
last_updated: 2026-03-01
title: Standards: Project Layout
purpose:
  Canonical folder layout + placement rules across 2bananas projects.
-->
# Standards: Project Layout

## Default top-level layout
Prefer these folders (create only what you need):

- `app/` (non-web application code)
- `api/` (service backend, if any)
- `web/` (public assets only)
- `scripts/` (repeatable utilities)
- `config/` (examples/templates; safe to commit)
- `secrets/` (real env; never commit)
- `data/` (SQLite/db/files; never in `web/`)
- `logs/` (log files)
- `docs/` (project docs)
- `tests/`
- `venv/` or `.venv/` (optional)

## Rules
- Keep secrets and databases out of `web/`.
- Prefer SQLite at `data/app.sqlite3` unless there’s a reason.
- Put env templates in `config/` (e.g. `settings.example.env`), real env in `secrets/.env` (chmod 600).
- Keep docs in `docs/` and add `docs/guides/` for project-specific guides.
