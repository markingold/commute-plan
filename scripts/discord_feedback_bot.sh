#!/usr/bin/env bash
set -eu

BASE="/srv/2bananas/projects/commute-plan"
PY="$BASE/venv/bin/python"
LOGDIR="$BASE/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/discord_feedback_bot.log"

{
  TS="$(date +%Y%m%d_%H%M%S)"
  echo "[$TS] === discord_feedback_bot start ==="
  echo "[$TS] cwd: $BASE"

  cd "$BASE"

  if [ ! -x "$PY" ]; then
    echo "[$TS] ❌ venv python not found at $PY"
    echo "[$TS] === discord_feedback_bot done (failure) ==="
    exit 1
  fi

  # Run the DM listener bot (blocking)
  exec "$PY" -m app.src.discord_feedback_bot
} >>"$LOG" 2>&1
