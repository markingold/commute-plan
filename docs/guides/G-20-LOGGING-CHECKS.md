<!--
id: G-20-LOGGING-CHECKS
version: 1.0
last_updated: 2026-03-16
title: Logging Checks
purpose:
  Verify structured logging baseline and HTTP request-id behavior.
related:
  - docs/guides/G-00-INDEX.md
  - app/src/logging_setup.py
  - app/src/comfort_api_server.py
-->
# Logging Checks

## When to use

- After logging or API middleware changes.
- When troubleshooting service observability issues.

## Steps

1. Start comfort API:

```bash
cd /srv/2bananas/projects/commute-plan
LOG_FORMAT=json venv/bin/python -m app.src.comfort_api_server --host 127.0.0.1 --port 8099
```

2. In a second terminal, send health request with custom request ID:

```bash
curl -i -H 'X-Request-Id: demo-req-123' http://127.0.0.1:8099/health
```

3. Verify response and logs:

- Response should include `X-Request-Id: demo-req-123`.
- JSON payload should include `ok`, `service`, `version`, `time`, `uptime_s`.
- Service log event should include `request_id`, `method`, `path`, `status`, `duration_ms`.

## Pitfalls

- Do not log token values from Discord/OpenWeather env keys.
- If logs are console format, set `LOG_FORMAT=json` before startup.
