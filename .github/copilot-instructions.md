<!--
id: COPILOT-INSTRUCTIONS
version: 1.2
last_updated: 2026-03-01
title: 2bananas Copilot Instructions (Template)
purpose:
  Repo-wide Copilot rules for any 2bananas project. Keep practical; link to docs for details.
usage:
  This template is copied into each repo at .github/copilot-instructions.md by sync_to_repos.sh
-->
# 2bananas Copilot Instructions

This repo is part of the **2bananas** ecosystem (local-first, long-lived small tools).

## Golden rules
- Prefer simple, readable solutions.
- Avoid new dependencies unless clearly worth it.
- Keep changes small; don’t break existing behavior silently.
- Add useful logs; never log secrets/tokens/keys.

## House structure (file placement)
Follow: `docs/2bananas/STANDARDS_PROJECT_LAYOUT.md`

Key rules:
- Keep secrets + DB out of `web/`.
- Prefer SQLite at `data/app.sqlite3` unless there’s a reason.
- Env templates in `config/`, real env in `secrets/.env` (chmod 600).

## Logging (expected everywhere)
Follow: `docs/2bananas/STANDARDS_LOGGING.md`

Minimum:
- include `ts`, `level`, `msg`, `project`, `component`
- for HTTP: `request_id`, `duration_ms`, `status`, `path`, `method`
- accept `X-Request-Id` if present; generate otherwise; echo back

## Global env keys
Shared keys live in: `/srv/2bananas/secrets/global.env`
Doc reference: `docs/2bananas/OPS_GLOBAL_ENV.md`

Rule:
- reuse existing key names when possible (don’t invent new ones casually)

## Services / ports
- Prefer ports that are already standardized via global env keys.
- When adding a long-lived service, ensure it has a health check and logs are discoverable.
References:
- `docs/2bananas/OPS_SERVICES.md`
- `docs/2bananas/OPS_PORTS.md`
- banana-monitor handbook: `docs/2bananas/apps/banana-monitor/README.md`

## Documentation
Follow: `docs/2bananas/STANDARDS_DOCS.md`

Rule:
- If you change behavior, update README and any relevant guides.

## Guides format (when writing procedures)
Follow: `docs/2bananas/GUIDE_SYSTEM.md`

Rule:
- Use short headers (`id`, `version`, `last_updated`, `title`, `purpose`)
- Keep guides readable and command-oriented.
