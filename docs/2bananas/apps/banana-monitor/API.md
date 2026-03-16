<!--
id: APP-BANANA-MONITOR-API
version: 1.2
last_updated: 2026-03-01
title: banana-monitor API Reference
purpose:
  Public HTTP surface exposed by banana-monitor. Keep in sync with app/main.py.
-->
# API Reference

This document describes the public HTTP surface exposed by banana-monitor.

Note: the canonical list of routes lives in `app/main.py`. If routes change, update this document in the same PR.

## Base URL

- Local dev: `http://127.0.0.1:<BM_PORT>/`
- Behind a proxy: `https://yourdomain/<prefix>/` (set `APP_URL_PREFIX` accordingly)

## Authentication (optional)

If `BM_API_KEY` is set, requests must include one of:

- `X-API-Key: <key>`
- `Authorization: Bearer <key>`
- `Authorization: Bot <key>`

If `BM_API_KEY` is empty/unset, auth is disabled.

## Endpoints

### Health

- `GET /health`
  - Liveness status for the API process

### Services list + status

- `GET /services`
  - Returns the curated service list with computed status fields.
  - Common fields include:
    - `id`, `label`, `group`, `order`, `ports`
    - `status` (derived; fields vary by adapter)

### Service action

- `POST /services/<service_id>/<action>`
  - Typical actions: `start`, `stop`, `restart`
  - The backend applies guardrails (type checks, enabled checks, etc.).

### Service logs

- `GET /services/<service_id>/logs?lines=200`
  - Fetch recent journalctl output for the service's unit.
  - `lines` query param controls how many lines to return (10–2000, default 200).

- `GET /services/<service_id>/tail?lines=200`
  - Semantic alias for `/logs` — identical behaviour and response shape.
  - The UI uses `/tail` for its polling loop so servers/proxies can distinguish
    one-shot log views from continuous polling if needed.

### Update service (config-driven)

- `POST /update-service`
  - Updates a specific service config entry (if supported/enabled in code)
  - Intended for safe, minimal updates (not a full editor)

### Reload configuration

- `POST /reload-config`
  - Reloads `config.json` without restarting the process

### Group actions

- `POST /groups/<group_id>/start`
- `POST /groups/<group_id>/stop`
  - Starts/stops all services in a group (guardrails apply)

- `POST /groups/start-all`
- `POST /groups/stop-all`
  - Starts/stops all eligible services across groups

### Alerts (optional)

- `GET /alerts/status`
  - Returns current alert subsystem status (if configured)

- `POST /alerts/test`
  - Trigger a test notification (if configured)

### Service Discovery

- `GET /discover-services`
  - Lists systemd service units on the machine that are **not** already in
    `config.json`. Filters out low-level system plumbing. Returns an array
    of `{ unit, active_state, sub_state, description }`.

- `POST /add-service`
  - Adds a new entry to `config.json`. Body: `{ unit, id?, label?, group?, ports?, enabled? }`.
    Returns the newly created service entry with live status.

## Error model

Common patterns:
- `200` for success responses
- `4xx` for validation/auth failures
- `5xx` for backend errors talking to systemd/journal/etc.

## Regenerating this doc

banana-monitor intentionally keeps documentation low-magic. If you add/change routes:
- update `docs/API.md` and `docs/openapi.yaml` in the same PR
- include a short test plan in the PR description
