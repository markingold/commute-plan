commute-plan
============

Status update (2026-03-16)
--------------------------

- Phase 1 logging foundation implemented with structured JSON logging.
- Health contract expanded: `/health` now includes `version`, `time`, `uptime_s`.
- Added `/version` endpoint.
- Added contract tests in `tests/contract/test_health.py`.
- Added smoke script in `scripts/smoke.sh`.
- Added project guides index in `docs/guides/G-00-INDEX.md`.

Quick verification
------------------

```bash
cd /srv/2bananas/projects/commute-plan
venv/bin/pip install -r requirements.txt -r requirements-dev.txt
venv/bin/python -m pytest -q tests/contract/test_health.py
scripts/smoke.sh
```

Small helper service that fetches OpenWeather One Call data for Tulsa, analyzes
your usual walking commute windows, and sends concise Discord DMs to help you
decide whether to walk or drive (and what to wear / whether to bring an umbrella).

It also exposes a small local web dashboard for running the planner, seeing a
weekly overview at a glance, and editing commute thresholds via a GUI.

Current behavior
----------------

- Uses OpenWeather One Call 3.0 for Tulsa, OK (or any configured lat/lon).
- Caches the latest forecast JSON in:

        /srv/2bananas/projects/commute-plan/data/tulsa_weather.json

- Builds daily commute plans based on:
  - Morning departure window (e.g., 07:00 ± 30 minutes).
  - Afternoon departure window (e.g., 15:30 ± 30 minutes).
- Uses hourly data (and optional OpenWeather minutely + daily data) to:
  - Suggest outerwear (e.g., `tshirt`, `long_sleeve`, `jacket`, `coat`).
  - Decide whether to bring an umbrella.
  - Decide whether walking is reasonable for each leg (`walk_ok`).
  - Compute a `walk_score` per leg:
    - `ok` – walking looks fine.
    - `caution` – borderline (rain or wind is marginal).
    - `avoid` – probably better to drive.
- Optionally refines the *morning* departure time using minute-by-minute
  precipitation to nudge you a few minutes earlier/later if it dodges a shower.
- Supports a weekly overview JSON output:
  - Summarizes the next N days (default 5) with AM/PM temperature, POP,
    wind, outerwear, and walk_score per day.
  - Used by the local web dashboard to render an emoji/temperature weekly grid.
- Sends a short, human-readable summary + detailed plan to Discord via DM
  using a bot (Nova) and your user ID.
- Only sends a DM if the plan meaningfully changed versus the last saved plan,
  to avoid spammy notifications.
- Provides a local-only web dashboard (dark mode) with:
  - A "Planner" tab (run CLI modes and view output).
  - A weekly emoji/temperature overview card.
  - A GUI config editor for commute thresholds.
  - A raw TOML editor for advanced tweaking.

Architecture overview
---------------------

Key pieces:

- app/src/weather_update.py  
  Fetches One Call 3.0 data from OpenWeather for your configured coordinates,
  normalizes units (Fahrenheit, mph, inches, etc.), and saves to
  `data/tulsa_weather.json` with a small `_units` block describing the units.

- app/src/weather_reader.py  
  Loads the cached JSON from `data/tulsa_weather.json`, handles timezone-aware
  conversion to local time (America/Chicago by default), and exposes helpers to
  the planner:
  - Hourly helpers: next N hours as typed objects.
  - Minutely helpers: next N minutes (for morning refinement).
  - Daily helpers: next N days (for weekly overview fallback when hourly data
    runs out).

- app/src/planner.py  
  Core logic that:
  - Scans the hourly forecast.
  - Picks the best forecast points inside your morning/afternoon windows.
  - Optionally refines the morning departure with minute-by-minute rain data.
  - Applies thresholds to determine:
    - `walk_ok`
    - `outerwear`
    - `umbrella`
    - `walk_score` ("ok" / "caution" / "avoid", based on rain + wind).
  - Returns a structured `DayPlan` object and helpers for:
    - Daily morning/evening runs (`build_day_plan`).
    - Weekly overview (`build_week_overview`), which combines:
      - Hourly data where available.
      - Daily data as a fallback for later days.

- app/src/planner_utils.py  
  Utilities for turning a `DayPlan` into nicely formatted text suitable for a
  Discord message and CLI output.

- app/src/cli.py  
  Command-line entry point to quickly test and inspect plans without sending
  Discord messages. Modes:
  - `test`        – prints configuration info, no plan.
  - `evening`     – builds a plan for tomorrow (evening-style run).
  - `morning`     – builds a plan for today (morning-style run).
  - `weekly_json` – prints a JSON weekly overview for the dashboard:
    - Includes per-day AM/PM temps, feels-like, POP, wind, outerwear, walk_score.
    - Used by the web dashboard to render the weekly grid.

- app/src/notifier.py  
  Orchestrates:
  - Building a plan (morning/evening).
  - Comparing the new plan to the last saved one.
  - Deciding whether the change is “meaningful.”
  - Sending a DM via Discord if appropriate.

  It stores the last plan in:

        data/last_plan.json

- app/src/discord_client.py  
  Small helper that:
  - Loads secrets from `secrets/.env` (and/or process env).
  - Creates (or reuses) a DM channel with your Discord user ID.
  - Sends the commute summary as a message to that DM.

- app/src/config_loader.py (if present)  
  Shared loader for environment variables and config paths used by the planner,
  notifier, and dashboard. Centralizes things like `secrets/.env` resolution,
  timezone, and weather JSON location.

- scripts/commute_evening.sh  
  Wrapper script for cron that:
  - Activates the virtualenv.
  - Runs the weather update.
  - Runs the evening notifier (tomorrow’s plan).
  - Logs output to `logs/cron_evening.log`.

- scripts/commute_morning.sh  
  Wrapper script for cron that:
  - Activates the virtualenv.
  - Runs the weather update.
  - Runs the morning notifier (today’s plan).
  - Logs output to `logs/cron_morning.log`.

- web/index.php  
  Local web dashboard (dark-mode, single-page) that:
  - Shows a "Planner" card:
    - Radio buttons for modes: `test`, `evening`, `morning`, `weekly_json`.
    - Runs `venv/bin/python -m app.src.cli <mode>` under the hood.
    - Displays the raw CLI output for debugging.
  - Shows a "Weekly overview" card:
    - Calls `weekly_json` from the CLI on page load.
    - Renders a multi-day table with:
      - Day + date.
      - AM / PM outerwear + walk emoji.
      - Inline temperature, feels-like, POP, and wind/gusts.
  - Provides a GUI config editor:
    - Drives off a `CONFIG_SCHEMA` in PHP that mirrors the Python thresholds.
    - Reads/writes `secrets/commute_config.toml` in a canonical format.
  - Provides a raw TOML editor:
    - Direct textarea view over `secrets/commute_config.toml`.
    - Writes back to disk and re-syncs the GUI view.
  - Uses simple CSRF protection for POST actions.

- logs/  
  Contains:
  - `logs/steps/…` – one-off setup/patch logs.
  - `logs/cron_evening.log` – appended to by `commute_evening.sh`.
  - `logs/cron_morning.log` – appended to by `commute_morning.sh`.

Configuration
-------------

Environment variables are primarily loaded from:

    /srv/2bananas/projects/commute-plan/secrets/.env

Expected keys (minimum):

- OpenWeather:

  - `OPENWEATHER_API_KEY` – your One Call 3.0 API key.
  - `OPENWEATHER_LAT`     – latitude (e.g. 36.154 for Tulsa).
  - `OPENWEATHER_LON`     – longitude (e.g. -95.9928 for Tulsa).
  - Optional: `OPENWEATHER_UNITS` (if you want to override; internal logic
    normalizes to US units regardless).

- Discord (Nova bot):

  - `DISCORD_BOT_TOKEN`       – bot token for Nova.
  - `DISCORD_USER_ID_MARK`    – your personal Discord user ID (for DMs).
  - `DISCORD_APP_ID`          – app ID (optional, for logging/diagnostics).
  - `DISCORD_PUBLIC_KEY`      – public key (optional, for logging/diagnostics).

- Commute / environment (optional):

  - `APP_ENV`        – e.g. `dev` or `prod` (used for logging tweaks).
  - `TZ`             – preferred timezone key (defaults to America/Chicago if not set).
  - `TIMEZONE`       – legacy fallback key (kept for backward compatibility).
  - `WORK_DAYS`      – comma-separated list of work days (e.g. `Mon,Tue,Wed,Thu,Fri`).
  - `WEATHER_JSON`   – optional override for the weather JSON path.

The weather JSON is now owned by this project and lives at:

    /srv/2bananas/projects/commute-plan/data/tulsa_weather.json

It no longer depends on the smart_assistant’s weather module for cached data.

Commute thresholds and minutely behavior are configured in TOML via:

- Example/template:

        /srv/2bananas/projects/commute-plan/commute_config.example.toml

- Real config (used by both Python and the web dashboard):

        /srv/2bananas/projects/commute-plan/secrets/commute_config.toml

The web dashboard’s GUI editor rewrites `secrets/commute_config.toml` using a
canonical layout based on the PHP `CONFIG_SCHEMA`.

Project layout
--------------

Key directories:

- `/srv/2bananas/projects/commute-plan/app/src/`  
  Python source (weather update, reader, planner, notifier, Discord client, CLI).

- `/srv/2bananas/projects/commute-plan/web/`  
  - `index.php` – local web dashboard (Planner + Weekly overview + Config GUI + raw TOML).

- `/srv/2bananas/projects/commute-plan/data/`  
  - `tulsa_weather.json` – latest cached forecast.
  - `last_plan.json`     – last sent commute plan (for diffing).

- `/srv/2bananas/projects/commute-plan/secrets/`  
  - `.env`                     – environment / secrets.
  - `commute_config.toml`      – real commute thresholds used by planner + dashboard.

- `/srv/2bananas/projects/commute-plan/scripts/`  
  - `commute_evening.sh` – cron wrapper.
  - `commute_morning.sh` – cron wrapper.

- `/srv/2bananas/projects/commute-plan/logs/`  
  - `cron_evening.log`, `cron_morning.log` (runtime logs).
  - `steps/` (manual setup/patch logs).

Quick start (CLI + daemon)
--------------------------

1. Create and activate virtualenv:

        cd /srv/2bananas/projects/commute-plan
        python3 -m venv venv
        source venv/bin/activate

2. Install requirements:

        pip install -r requirements.txt

3. Create `secrets/.env` with the required keys (OpenWeather + Discord).

4. Test imports and basic config:

        cd /srv/2bananas/projects/commute-plan
        source venv/bin/activate
        python -m app.src.cli test

5. Manually run an evening plan (uses existing `data/last_plan.json` and
   `data/tulsa_weather.json` if present):

        python -m app.src.cli evening

Weather update and planner usage
--------------------------------

To fetch fresh weather data and save it:

    cd /srv/2bananas/projects/commute-plan
    source venv/bin/activate
    python -m app.src.weather_update

This should print a line like:

    ✓ Saved /srv/2bananas/projects/commute-plan/data/tulsa_weather.json (... bytes) [YYYY-MM-DD HH:MM:SS]

To build a plan for tomorrow (evening run):

    python -m app.src.cli evening

To build a plan for today (morning run):

    python -m app.src.cli morning

To generate a JSON weekly overview (used by the web dashboard):

    python -m app.src.cli weekly_json

This prints something like:

    {
      "generated_at": "...",
      "days": [
        {
          "date": "2025-11-18",
          "weekday": "Tue",
          "morning": {
            "leave_time_local": "2025-11-18T07:00:00",
            "temp_f": 62.6,
            "feels_like_f": 61.7,
            "pop": 0,
            "wind_speed_mph": 8.2,
            "wind_gust_mph": 20.9,
            "outerwear": "long_sleeve",
            "walk_score": "ok"
          },
          "afternoon": {
            "leave_time_local": "2025-11-18T16:00:00",
            "temp_f": 73.7,
            "feels_like_f": 72.2,
            "pop": 0,
            "wind_speed_mph": 4.7,
            "wind_gust_mph": 7.4,
            "outerwear": "tshirt",
            "walk_score": "ok"
          }
        },
        ...
      ]
    }

Notifier usage (Discord DMs)
----------------------------

The notifier is the piece that actually decides whether to send a Discord DM.

Dry-run (shows message, never sends, never mutates `last_plan.json`):

    cd /srv/2bananas/projects/commute-plan
    source venv/bin/activate
    python -m app.src.notifier --dry-run evening
    python -m app.src.notifier --dry-run morning

Real run (respects "meaningful change" logic and may send DM):

    python -m app.src.notifier evening
    python -m app.src.notifier morning

Force send (bypass change detection, useful for testing):

    python -m app.src.notifier --force evening
    python -m app.src.notifier --force morning

“Meaningful change” includes things like:

- Date changed (e.g. 2025-11-16 -> 2025-11-17).
- Morning recommendation becoming available/unavailable.
- Afternoon recommendation becoming available/unavailable.
- Noticeable temperature changes across the commute windows.
- Potential changes in umbrella / walk_ok / walk_score status.

Web dashboard (optional)
------------------------

The project includes a small, local-only web dashboard in `web/index.php`.

High-level behavior:

- Planner tab:
  - Lets you run the same CLI modes as the shell (`test`, `evening`, `morning`,
    `weekly_json`) via a simple form.
  - Shows the raw CLI output in a dark-themed panel for debugging.

- Weekly overview card:
  - Automatically runs `weekly_json` via the CLI.
  - Renders a 5-day (or N-day) grid that shows:
    - Day + date.
    - AM / PM:
      - Outerwear + walk emoji:
        - Clothing: `🧥` heavy coat · `🧶` light jacket · `👕` tee/long-sleeve · `🩳👕` shorts.
        - Walk: `✅` ok · `⚠️` borderline/caution · `🚫` probably drive.
      - Inline temperature and feels-like.
      - POP (% chance of precip).
      - Wind / gust speeds.

- Config (GUI) tab:
  - Renders a form based on `CONFIG_SCHEMA` in PHP.
  - Lets you change:
    - Morning/afternoon departure times and flex windows.
    - Temperature thresholds.
    - Rain thresholds (umbrella vs avoid walking).
    - Wind thresholds.
    - Minutely refinement parameters.
    - Change sensitivity thresholds for "meaningful" updates.
    - Alert cooldowns and failure streak thresholds.
  - When saved:
    - Writes a canonical `secrets/commute_config.toml`.
    - Keeps the raw-editor view in sync.

- Config (raw) tab:
  - Shows the raw TOML for `secrets/commute_config.toml`.
  - Lets you paste or edit directly.
  - On save:
    - Writes the file.
    - Re-parses into the GUI view so both stay aligned.

To use the dashboard:

- Serve the `web/` directory via your local web server (Apache, Nginx, etc.).
- Point a browser at the configured URL (e.g. `https://your-host/commute-plan/`).
- Ensure PHP has permission to:
  - Run `venv/bin/python` as configured in `web/index.php`.
  - Read and write `secrets/commute_config.toml`.
  - Read `data/*.json` and `logs/` (for troubleshooting).

Cron setup
----------

Example cron entries (adjust times as desired):

- Evening run – look at tomorrow’s commute and DM if it changed
  (e.g. Sun–Thu at 19:15):

        15 19 * * 0-4 /srv/2bananas/projects/commute-plan/scripts/commute_evening.sh >/dev/null 2>&1

- Morning run – check today’s commute for last-minute changes
  (e.g. Mon–Fri at 06:15):

        15 6  * * 1-5 /srv/2bananas/projects/commute-plan/scripts/commute_morning.sh >/dev/null 2>&1

The scripts themselves:

- Activate the project’s venv.
- Run the weather update.
- Run the notifier in the appropriate mode.
- Pipe output via `tee` to:

  - `logs/cron_evening.log`
  - `logs/cron_morning.log`

Checking logs
-------------

To inspect the most recent evening run:

    cd /srv/2bananas/projects/commute-plan
    tail -n 100 logs/cron_evening.log

To inspect the most recent morning run:

    tail -n 100 logs/cron_morning.log

There are also one-off setup/patch logs in `logs/steps/` for a historical
record of how the project was configured.

Future ideas
------------

Possible enhancements:

- Better weekend handling:
  - Skip DMs entirely on non-workdays, or
  - Send fun “no commute today” messages.
- Smarter thresholds:
  - Personalized comfort ranges (temperature, wind, rain).
  - Season-aware rules (different logic for winter vs summer).
- Nova integration:
  - Add an HTTP or direct-module bridge so the main Smart Assistant can answer:
    “What’s my commute like tomorrow?” using this project’s logic.
- Web UI extras:
  - Show today/tomorrow commute cards side-by-side in the dashboard.
  - Display a small history of recent plans and whether you walked or drove.
  - Inline toggles for forcing a re-check / re-send.
  - Simple debug panel that surfaces the latest cron/notifier logs.

For now, commute-plan operates as a small, focused daemon: fetch weather, build
a plan, and DM you when it actually matters—plus a local dashboard so you can
peek under the hood and tweak the thresholds without leaving your browser.
