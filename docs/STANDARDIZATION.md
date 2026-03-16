# commute-plan — Standardization Plan

## Status Update (2026-03-16)

This plan started as a generated baseline and had drift vs current implementation.

Completed since initial draft:

- Git baseline established for this workspace and linked to new remote repo.
- Structured logging foundation implemented across core runtime modules.
- Health contract expanded in comfort API (`/health` now includes `version`, `time`, `uptime_s`).
- Added `GET /version` endpoint.
- Added contract tests under `tests/contract/` and smoke script at `scripts/smoke.sh`.
- Added env template updates (`LOG_FORMAT`, `TZ`, project-local `WEATHER_JSON`).

Still in progress / pending additional standardization:

- Full UI component/token migration to complete 2b conventions.
- Final docs cleanup and phase closeout updates across README/guides.

Use this section as the source of truth over stale generated assumptions below.

> Generated 2026-02-28 from the ecosystem-wide audit.
> Historical baseline: implementation is now in progress and has already completed multiple items above.

---

## Project Overview

| Attribute | Current State |
|-----------|--------------|
| **Framework** | stdlib `http.server` (SimpleHTTPRequestHandler) |
| **Database** | SQLite |
| **CLI** | argparse (8 standalone scripts) |
| **Tests** | None |
| **Health endpoint** | `/health` — **partially compliant** |
| **Web UI** | PHP + inline CSS/JS, dark theme, sky-blue accent, CSS variables |

---

## 1) Health Endpoint

**Current:** `GET /health` → `{"ok": true, "service": "commute-plan-api", "uptime": N}` — partial compliance. Missing `version`, `time`; uses `uptime` not `uptime_s`.

### Changes

| # | Task | Effort |
|---|------|--------|
| 1 | Add `version` field | Small |
| 2 | Add `time` field (ISO 8601) | Small |
| 3 | Rename `uptime` → `uptime_s` | Small |
| 4 | Add `GET /version` endpoint | Small |
| 5 | Add `tests/contract/test_health.py` | Small |

---

## 2) API Routes

**Current:** stdlib HTTP server with manual route parsing.

| Route | Method | Notes |
|-------|--------|-------|
| `/health` | GET | Partially compliant |
| `/api/commute` | GET | ✅ |
| `/api/history` | GET | ✅ |
| `/api/alerts` | GET | ✅ |
| `/api/schedule` | GET | ✅ |

### Changes

| # | Task | Effort |
|---|------|--------|
| 1 | Ensure all responses use `{ok, data}` / `{ok, error}` envelope | Medium |
| 2 | Route structure is simple and clean — no major changes needed | None |

---

## 3) Testing

**Current:** None.

### Changes

| # | Task | Effort |
|---|------|--------|
| 1 | Create `tests/contract/test_health.py` | Small |
| 2 | Create `scripts/smoke.sh` — start server, hit health, verify response | Small |
| 3 | Add `requirements-dev.txt` with `pytest`, `httpx` | Small |

---

## 4) CLI & Scripts

**Current:** 8 argparse scripts: `check_road_conditions.py`, `fetch_commute.py`, `fetch_wx.py`, `manage_routes.py`, `notify_commute.py`, `report_commute.py`, `schedule_alerts.py`, `sync_calendars.py`

### Changes

| # | Task | Effort |
|---|------|--------|
| 1 | Add `--version` flag to all 8 scripts | Small |
| 2 | Add `--dry-run` where applicable | Small |
| 3 | Create `scripts/run_api.sh` | Small |
| 4 | Create `scripts/smoke.sh` | Small |

---

## 5) Environment Variables

**Current .env keys:** `GOOGLE_MAPS_API_KEY`, `OPENWEATHER_API_KEY`, `PUSHOVER_TOKEN`, `PUSHOVER_USER`, `TIMEZONE`

### Changes

| # | Variable | Change | Effort |
|---|----------|--------|--------|
| 1 | `APP_ENV` | **Add** — missing | Small |
| 2 | `APP_NAME` | **Add** — set to `commute-plan` | Small |
| 3 | `APP_VERSION` | **Add** | Small |
| 4 | `LOG_LEVEL` | **Add** — missing | Small |
| 5 | `LOG_DEST` | **Add** — missing | Small |
| 6 | `LOG_FORMAT` | **Add** — missing | Small |
| 7 | `TIMEZONE` | **Rename** → `TZ` (POSIX standard) | Small |

---

## 6) Web UI

**Current:** PHP + inline CSS/JS. Dark theme with CSS variables. Sky-blue accent. Single-column with card layout.

### Changes

| # | Task | Effort |
|---|------|--------|
| 1 | Replace existing CSS vars with `--2b-*` tokens (partial overlap likely) | Medium |
| 2 | Set `--2b-accent: #38bdf8;` (sky-blue) | Small |
| 3 | Add `2b-header` with project name + "← Lab" link | Small |
| 4 | Replace card styles with `2b-card` | Small |
| 5 | Move inline CSS to external stylesheet | Medium |
| 6 | Move inline JS to external file | Medium |
| 7 | Add dark/light toggle using `[data-theme]` | Medium |
| 8 | Create `web/lab.meta.json` | Small |

**lab.meta.json:**
```json
{
  "title": "Commute Plan",
  "description": "Commute tracking, road conditions, and weather-based alerts.",
  "category": "app",
  "tags": ["php", "stdlib-http", "sqlite"],
  "healthPath": "/health",
  "accent": "#38bdf8"
}
```

---

## 7) Phasing

| Phase | Items | Week |
|-------|-------|------|
| 1 — Foundation | Smoke script | 1-2 |
| 2 — Health & Testing | Fix health fields, add contract test | 3-4 |
| 3 — Env Vars | Add `APP_*`/`LOG_*`, rename `TIMEZONE` → `TZ` | 5-6 |
| 4 — Web UI | Extract inline CSS/JS, adopt `--2b-*` tokens | 6-7 |
| 5 — CLI | Add `--version` to 8 scripts | 9+ |

---

## 8) Error Tracking

Create `docs/DECISIONS.md`.
Reference global `docs/error-patterns.md`.

Normalize any env vars as part of this project:
IF any of these env var’s are used in this project, and they do not already fit the standard naming, use this an an opportunity to migrate it to use the naming as discussed below, and make any minor modifications to the code to use the new standards if not already used.  Each change should be tested to ensure it’s still all working correctly after standardization:.env var Standardization report
Use these canonical names everywhere for simplicity:
* Pushover
    * Standardize to: PUSHOVER_USER_KEY, PUSHOVER_APP_TOKEN
    * Currently seen as: PUSHOVER_USER, PUSHOVER_USER_KEY, PUSHOVER_TOKEN, PUSHOVER_APP_TOKEN, PUSHOVER_API_KEY
* Spotify
    * Standardize to: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI
    * Currently seen as: SPOTIFY_API_KEY, SPOTIFY_API_SECRET, SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI
* OpenWeather
    * Standardize to: OPENWEATHER_API_KEY
    * Currently seen as: OPENWEATHER_API_KEY, OPENWEATHERMAP_API_KEY
    * Conflict: two different values appear (e4fd... and 8409...). Pick one real account and make all projects use that same key name/value.
* Google provider keys
    * Standardize to: GOOGLE_MAPS_API_KEY, GOOGLE_PLACES_API_KEY
    * Currently seen as: GOOGLE_MAPS_API_KEY, GOOGLE_PLACES_API_KEY, GOOGLE_API_KEY
    * GOOGLE_API_KEY is ambiguous and should be removed.
* Amadeus
    * Standardize to: AMADEUS_API_KEY, AMADEUS_API_SECRET
    * Currently seen as: AMADEUS_API_SECRET, AMADEUS_SECRET
* OpenRouter
    * Standardize to: OPENROUTER_BASE_URL, OPENROUTER_API_KEY
    * Currently seen as: OPENROUTER_API_KEY, LLM_OPENROUTER_API_KEY, SYSOP_OPENROUTER_API_KEY, REMOTE_LLM_API_KEY, LLM_API_KEY (when actually used for OpenRouter)
* Generic local LLM endpoint
    * Standardize to: LOCAL_LLM_BASE_URL, LOCAL_LLM_CHAT_COMPLETIONS_URL
    * Currently seen as: LLM_CHAT_API_BASE, CODE_INDEXER_LLM_BASE_URL, LLM_API_URL, LLM_LOCAL_URL, LOCAL_LLM_URL, AI_ENDPOINT, LORA_INTENT_URL, LLM_LORA_URL
    * Keep project-specific overrides only when a project genuinely needs a different endpoint.
* Banana Monitor
    * Standardize to: BANANA_MONITOR_API_KEY
    * Currently seen as: BM_API_KEY, BANANA_MONITOR_API_KEY
* GitHub token
    * Standardize to: GITHUB_TOKEN
    * Currently seen as: GITHUB_TOKEN, GITHUB_API_KEY
* GNews
    * Standardize to: GNEWS_API_KEY
    * Currently seen as: GNEWS_API_KEY, GNEWS_TOKEN
* Tuya
    * Standardize to: TUYA_ACCESS_ID, TUYA_ACCESS_SECRET, TUYA_UID, TUYA_API_ENDPOINT
    * Currently seen as: TUYA_API_KEY, TUYA_API_SECRET, TUYA_SMART_LIFE_APP_UID, TUYA_ACCESS_ID, TUYA_ACCESS_KEY, TUYA_UID
    * TUYA_API_KEY/TUYA_API_SECRET should be retired in favor of the official access-id/secret naming.
* Picolabs
    * Standardize to: PICOLABS_API_KEY
    * Currently seen as: PICOLABS_API_KEY, ACCESS_KEY
    * ACCESS_KEY is too generic and should be removed.
* Discord channel
    * Standardize to: DISCORD_CHANNEL_ID for numeric Discord snowflakes only
    * Currently seen as: DISCORD_CHANNEL_ID=145712... and also DISCORD_CHANNEL_ID=media-server
    * If you want a channel name fallback, create a separate DISCORD_CHANNEL_NAME.
* Plex
    * Standardize to: PLEX_URL, PLEX_TOKEN, PLEX_SERVER_ID
    * You currently have both a raw LAN URL and a plex.direct URL, plus two different tokens.
    * Pick one default global set, then only override per-project if a project truly needs the alternate endpoint.
* NVIDIA NIM
    * Standardize to: NVIDIA_NIM_API_KEY
    * Currently seen as: NVIDIA_NIM_NEW_API_KEY
    * Cleaner to drop “NEW” from the name unless you truly have multiple NIM accounts.
* Discord webhooks
    * Standardize to: DISCORD_LOW_WEBHOOK, DISCORD_HIGH_WEBHOOK, plus optional single DISCORD_WEBHOOK_URL
    * Keep only the single generic one if a project does not need priority routing.
