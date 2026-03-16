<!--
id: OPS-TROUBLESHOOTING
version: 1.2
last_updated: 2026-03-01
title: Ops: Troubleshooting
purpose:
  Standard “first 5 minutes” checks for any project/service.
-->
# Ops: Troubleshooting

## Quick triage
- Check port/listeners: see [Ports](./OPS_PORTS.md)
- Check service health endpoint: `curl -sS http://127.0.0.1:<PORT>/health || true`
- Check logs:
  - journald: `journalctl -u <service> -n 200 --no-pager`
  - file logs: `tail -n 200 logs/*.log 2>/dev/null || true`

## Common causes
- wrong env keys / missing env
- port conflict
- permissions on `secrets/.env` or `data/`
