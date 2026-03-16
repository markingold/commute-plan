#!/usr/bin/env bash
set -euo pipefail

BASE="/srv/2bananas/projects/commute-plan"
HOST="127.0.0.1"
PORT="${1:-18100}"

cd "$BASE"

if [[ -x "$BASE/venv/bin/python" ]]; then
  PY="$BASE/venv/bin/python"
else
  PY="python3"
fi

LOGFILE="$(mktemp)"

cleanup() {
  if [[ -n "${API_PID:-}" ]] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
  rm -f "$LOGFILE"
}
trap cleanup EXIT

LOG_FORMAT=json "$PY" -m app.src.comfort_api_server --host "$HOST" --port "$PORT" >"$LOGFILE" 2>&1 &
API_PID=$!

for _ in $(seq 1 40); do
  if curl -fsS "http://$HOST:$PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

HEALTH_JSON="$(curl -fsS -H 'X-Request-Id: smoke-health' "http://$HOST:$PORT/health")"
VERSION_JSON="$(curl -fsS "http://$HOST:$PORT/version")"

python3 - "$HEALTH_JSON" "$VERSION_JSON" <<'PY'
import json
import sys

health = json.loads(sys.argv[1])
version = json.loads(sys.argv[2])

required_health = ["ok", "service", "version", "time", "uptime_s"]
missing = [k for k in required_health if k not in health]
if missing:
    raise SystemExit(f"health missing keys: {missing}")

if health["ok"] is not True:
    raise SystemExit("health ok != true")
if version.get("ok") is not True:
    raise SystemExit("version ok != true")
if not isinstance(version.get("version"), str):
    raise SystemExit("version field missing or invalid")

print("smoke: PASS")
PY
