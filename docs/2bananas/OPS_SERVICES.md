<!--
id: OPS-SERVICES
version: 1.2
last_updated: 2026-03-01
title: Ops: Services
purpose:
  How services are managed in the ecosystem (banana-monitor is the primary view).
-->
# Ops: Services

## Primary source
- banana-monitor handbook: [docs/2bananas/apps/banana-monitor](./apps/banana-monitor/README.md)

## Expectations
- Long-lived services should have:
  - a clear name
  - a health endpoint when applicable (`/health`)
  - logs discoverable via banana-monitor or journald
## banana-monitor API
- See: `docs/2bananas/apps/banana-monitor/API.md`

