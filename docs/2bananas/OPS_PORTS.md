<!--
id: OPS-PORTS
version: 1.2
last_updated: 2026-03-01
title: Ops: Ports
purpose:
  How to see what ports are in use and how to pick a new one.
-->
# Ops: Ports

## Quick checks
- What is listening?
  - `ss -ltnp | sed -n '1,200p'`
- Who owns a port?
  - `sudo lsof -iTCP:<PORT> -sTCP:LISTEN -Pn || true`

## Convention
- Prefer using shared port env keys from: [Global env keys](./OPS_GLOBAL_ENV.md)
- If you add a new long-lived service, document its port and make it visible in banana-monitor.
