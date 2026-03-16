#!/usr/bin/env bash
set -eu

BASE="/srv/2bananas/projects/commute-plan"
VENV="$BASE/venv/bin/activate"
LOGDIR="$BASE/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/cron_evening.log"

{
  TS="$(date +%Y%m%d_%H%M%S)"
  echo "[$TS] === commute-plan evening job start ==="

  # Always run from project root so 'app' package is importable
  cd "$BASE"

  # Activate venv if present
  if [ -f "$VENV" ]; then
    # shellcheck disable=SC1090
    . "$VENV"
  fi

  # 1) Fetch weather
  if ! python -m app.src.weather_update; then
    echo "[$TS] Error: weather_update failed"
    "$BASE/venv/bin/python" -m app.src.alerts weather_fail "Evening cron: weather_update failed" || true
    echo "[$TS] === commute-plan evening job done (failure) ==="
    exit 1
  fi
  echo "[$TS] weather_update: OK"
  "$BASE/venv/bin/python" -m app.src.alerts weather_ok || true

  # 2) Build & send evening plan (tomorrow)
  if python -m app.src.notifier --force evening; then
    echo "[$TS] notifier evening: OK"
  else
    echo "[$TS] notifier evening: FAILED"
  fi

  echo "[$TS] === commute-plan evening job done ==="
} >>"$LOG" 2>&1
