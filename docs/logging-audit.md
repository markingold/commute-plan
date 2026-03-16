# Logging Audit — commute-plan

## Status Update (2026-03-16)

Phase 1 logging foundation is now implemented in code:

- Added shared structured logging module: `app/src/logging_setup.py`
- Added `structlog` dependency in `requirements.txt`
- Replaced print-based runtime diagnostics with structured logs in:
    - `app/src/comfort_api_server.py`
    - `app/src/notifier.py`
    - `app/src/discord_client.py`
    - `app/src/discord_feedback_bot.py`
    - `app/src/weather_update.py`
    - `app/src/config_loader.py`
    - `app/src/planner.py`
    - `app/src/cli.py` (run-level structured events while preserving user output)

HTTP logging is now emitting request metadata with `request_id`, `method`, `path`, `status`, and `duration_ms` in `comfort_api_server`.

This file remains useful for follow-on hardening items, but "no logging" is no longer accurate.

**Generated:** 2026-02-28
**Standard reference:** `docs/copilot-instructions.md` §4
**Phase:** 4 (no logging — add from scratch)

---

## Target Standard

| Requirement | Detail |
|---|---|
| **Format** | Structured JSONL |
| **Output** | `logs/` dir; stdout for journald capture |
| **Fields (always)** | `ts`, `level`, `project_id`, `component`, `msg` |
| **Fields (HTTP)** | `request_id`, `duration_ms` |
| **Fields (batch)** | `run_id`, `duration_ms` |
| **request_id** | Accept `X-Request-Id` header, else generate; echo in response headers + logs |
| **Secrets** | Never log secrets |
| **Library** | `structlog` (preferred) or stdlib `logging` with JSON formatter |

---

## Current State

| Aspect | Status | Detail |
|---|---|---|
| **Library** | ❌ | No logging library used at all — every file uses bare `print()` |
| **Format** | ❌ | Plain text `print()` with manual prefixes like `[comfort_api_server]` |
| **Fields** | ❌ | No structured fields |
| **HTTP API** | ⚠️ | stdlib `http.server` (`BaseHTTPRequestHandler` + `ThreadingHTTPServer`) on port 8099 — not FastAPI |
| **HTTP request logging** | ❌ | No request logging |
| **request_id** | ❌ | Not present |
| **duration_ms** | ❌ | Not measured |
| **Secrets safety** | ⚠️ | Not audited — Discord tokens loaded from `.env` |
| **Log destination** | ❌ | No log files from app; cron wrappers redirect to `logs/cron_morning.log` and `logs/cron_evening.log` |
| **Retention** | ⚠️ | Cron log files covered by global logrotate; but no app-level rotation |
| **Systemd** | ✅ | `commute-plan-comfort-api.service` and `commute-plan-discord-feedback-bot.service` exist |

---

## Project Components

This is a multi-component project:

| Component | File | Type | Current output |
|---|---|---|---|
| **comfort-api** | `app/src/comfort_api_server.py` | HTTP API (stdlib) | `print()` |
| **discord-bot** | `app/src/discord_feedback_bot.py` | Long-running bot | `print()` |
| **discord-client** | `app/src/discord_client.py` | Shared DM sender | `print()` |
| **cli** | `app/src/cli.py` | CLI (morning/evening/weekly) | `print()` |
| **notifier** | `app/src/notifier.py` | Cron-driven plan sender | none |
| **planner** | `app/src/planner.py` | Core planning logic | none |
| **weather** | `app/src/weather_update.py` | Weather fetch + cache | none |
| **comfort-db** | `app/src/comfort_db.py` | SQLite helper | none |
| **comfort-cli** | `app/src/comfort_cli.py` | Comfort feedback CLI | `print()` |
| **comfort-seed** | `app/src/comfort_seed.py` | Test data seeder | `print()` |
| **alerts** | `app/src/alerts.py` | Weather failure tracking | none |
| **config** | `app/src/config_loader.py` | Config loader | `print()` |

---

## Files to Change

### 1. Create `app/src/logging_setup.py`
- Add `structlog` JSONL configuration
- Provide `setup_logging(component)` that returns a bound logger with `project_id="commute-plan"`

### 2. `app/src/comfort_api_server.py`
- Replace all `print()` calls with structured logger
- Add request timing + `request_id` to the handler
- Since this uses stdlib `http.server` (not FastAPI), add logging in `do_GET`/`do_POST` methods directly
- Consider migrating to FastAPI (per §2 of copilot-instructions)

### 3. `app/src/discord_feedback_bot.py`
- Replace all `print()` with structured logger
- Bind `component="discord-bot"`

### 4. `app/src/cli.py`
- Replace `print()` diagnostics with structured logger
- Bind `component="cli"`, add `run_id` for each invocation

### 5. `app/src/notifier.py`
- Add structured logger with `component="notifier"`, `run_id` per cron run

### 6. All remaining `app/src/*.py` files
- Replace `print()` with structured logger calls
- Each file should use `component=` matching its role

### 7. `requirements.txt`
- Add `structlog>=24.1`

### 8. Cron wrapper scripts
- `scripts/commute_morning.sh`, `scripts/commute_evening.sh` — can keep file redirection for backward compat, but the Python code should now emit JSONL to stdout (which journald captures)

---

## Cross-Cutting Issues

| Issue | Detail |
|---|---|
| **No shared logger** | No centralized logging across the ecosystem — each project rolls its own |
| **stdlib HTTP server** | Not FastAPI; request_id middleware requires manual implementation in handler methods |
| **Discord bot tokens** | Ensure `DISCORD_BOT_TOKEN` is never logged; add token redaction |

---

## Reference Template

### `logging_setup.py`

```python
import logging, os, sys, uuid, structlog

LEVELS = {"TRACE": 5, "DEBUG": 10, "INFO": 20, "WARN": 30, "WARNING": 30, "ERROR": 40}
logging.addLevelName(5, "TRACE")

def setup_logging(component: str = "app"):
    level = LEVELS.get(os.getenv("LOG_LEVEL", "INFO").upper(), 20)
    json_out = os.getenv("LOG_FORMAT", "json").lower() == "json"
    logging.basicConfig(level=level, handlers=[logging.StreamHandler(sys.stdout)])
    processors = [
        structlog.processors.TimeStamper(fmt="iso", key="ts"),
        structlog.processors.add_log_level,
        structlog.processors.EventRenamer("msg"),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer() if json_out else structlog.dev.ConsoleRenderer(),
    ]
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger().bind(project_id="commute-plan", component=component)
```

### Batch CLI usage (run_id)

```python
import uuid
run_id = uuid.uuid4().hex[:12]
log = setup_logging("cli").bind(run_id=run_id)
```

### Expected JSONL Output

```json
{"ts":"2026-02-28T14:22:01.123456Z","level":"info","project_id":"commute-plan","component":"notifier","msg":"morning plan sent","run_id":"abc123def456","duration_ms":3200}
```
