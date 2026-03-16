#!/usr/bin/env bash
set -eu

BASE="/srv/2bananas/projects/commute-plan"
# Ensure module imports work under cron (cwd may be different)
cd "$BASE"

VENV="$BASE/venv/bin/activate"
LOGDIR="$BASE/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/cron_morning.log"

{
  TS="$(date +%Y%m%d_%H%M%S)"
  echo "[$TS] === commute-plan morning job start ==="

  # Activate venv if present
  if [ -f "$VENV" ]; then
    # shellcheck disable=SC1090
    . "$VENV"
  fi

  # Keep local logs bounded; retention failures must not block commute jobs.
  "$BASE/scripts/log_retention.sh" 14 || true

  # 1) Fetch weather
  if ! python -m app.src.weather_update; then
    echo "[$TS] Error: weather_update failed"
    "$BASE/venv/bin/python" -m app.src.alerts weather_fail "Morning cron: weather_update failed"
    echo "[$TS] === commute-plan morning job done (failure) ==="
    exit 1
  fi
  echo "[$TS] weather_update: OK"
  "$BASE/venv/bin/python" -m app.src.alerts weather_ok || true

  # 2) Build & send morning plan (today)
  if python -m app.src.notifier morning; then
    echo "[$TS] notifier morning: OK"
  else
    echo "[$TS] notifier morning: FAILED"
  fi

  echo "[$TS] === commute-plan morning job done ==="
} >>"$LOG" 2>&1
