<!--
id: APP-BANANA-MONITOR
version: 1.2
last_updated: 2026-03-01
title: banana-monitor Handbook
purpose:
  What banana-monitor is and how other projects should integrate with it.
-->
# banana-monitor Handbook

## What it does
- Service status/health view
- Log access (journald)
- Start/stop/restart orchestration
- Optional alerts
- Service discovery + safe add-to-config flow

## Base URL / auth
- Use `BANANA_MONITOR_BASE_URL` when available
- Port: `BANANA_MONITOR_PORT` (see [Global env keys](../../OPS_GLOBAL_ENV.md))
- Optional auth key: `BM_API_KEY` (see API reference)

## API reference
- [API.md](./API.md)

## Integration expectations (for other projects)
- Long-lived services should expose `/health` if practical.
- Services should log to stdout (journald) unless there’s a reason for file logs.
- Ports should be tracked consistently (ideally visible in banana-monitor).
