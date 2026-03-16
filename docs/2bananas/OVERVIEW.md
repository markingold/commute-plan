<!--
id: DOC-OVERVIEW
version: 1.2
last_updated: 2026-03-01
title: 2bananas Ecosystem Overview
purpose:
  High-level description of the 2bananas ecosystem and how projects should behave.
-->
# 2bananas Ecosystem Overview

## What this is
A local-first, long-lived home lab ecosystem of small projects under:

- `/srv/2bananas/projects/<project>/`

Each project typically has:
- a `.codex.toml` in the repo root (identity)
- a `docs/` folder (project docs)
- consistent folder layout (see [Project layout](./STANDARDS_PROJECT_LAYOUT.md))
- consistent logging (see [Logging](./STANDARDS_LOGGING.md))

## Shared services
Some projects act as shared infrastructure:
- **banana-monitor**: service/health/log orchestration
- **llm-manager**: local model endpoints + switching

See the app handbooks:
- [banana-monitor](./apps/banana-monitor/README.md)
- [llm-manager](./apps/llm-manager/README.md)

## Non-negotiables
- Follow layout + naming conventions.
- Add useful logs; never log secrets.
- Prefer small changes; avoid unnecessary dependencies.
- Keep docs accurate when behavior changes.
