"""
app.src.alerts
--------------
Small helper module for commute-plan alerts.

Currently supports:
- Tracking consecutive weather_update failures.
- Sending a Discord DM when failures exceed a configured threshold.
- Resetting failure streak on success.

CLI usage:
    python -m app.src.alerts weather_fail "reason text"
    python -m app.src.alerts weather_ok
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from .config_loader import load_commute_config
from . import discord_client

BASE_DIR = Path(__file__).resolve().parents[2]
STATUS_FILE = BASE_DIR / "data" / "weather_status.json"


def _load_status() -> Dict[str, Any]:
    """
    Load the weather status JSON (failure streak, last DM time).
    """
    if not STATUS_FILE.is_file():
        return {"consecutive_failures": 0, "last_failure_dm_at": None}
    try:
        text = STATUS_FILE.read_text(encoding="utf-8")
        return json.loads(text)
    except Exception:
        return {"consecutive_failures": 0, "last_failure_dm_at": None}


def _save_status(status: Dict[str, Any]) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, indent=2), encoding="utf-8")


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _get_alert_config() -> Dict[str, Any]:
    """
    Read [alerts] config from commute_config.toml, with safe defaults.
    """
    cfg = load_commute_config()
    alerts = cfg.get("alerts", {}) or {}
    return {
        "streak_threshold": int(alerts.get("weather_fail_streak_threshold", 3)),
        "cooldown_minutes": int(alerts.get("weather_fail_cooldown_minutes", 60)),
    }


def handle_weather_fail(reason: str) -> int:
    """
    Increment failure streak and, if the threshold is reached and cooldown
    allows, send a DM about the failure.
    """
    status = _load_status()
    cfg = _get_alert_config()

    streak = int(status.get("consecutive_failures", 0)) + 1
    status["consecutive_failures"] = streak

    now = datetime.now()
    last_dm_at = _parse_iso(status.get("last_failure_dm_at"))
    threshold = cfg["streak_threshold"]
    cooldown = cfg["cooldown_minutes"]

    should_dm = False
    if streak >= threshold:
        if last_dm_at is None:
            should_dm = True
        else:
            delta_min = (now - last_dm_at).total_seconds() / 60.0
            if delta_min >= cooldown:
                should_dm = True

    if should_dm:
        message_lines = [
            "⚠️ Commute-plan warning:",
            "",
            f"- Weather update has failed {streak} time(s) in a row.",
            f"- Most recent reason: {reason or '(no reason provided)'}",
            "",
            "I'll keep trying on the next scheduled run, but today's plan may be stale.",
        ]
        msg = "\n".join(message_lines)
        ok = discord_client.send_message(msg)
        if ok:
            # Reset streak after notifying and record DM timestamp.
            status["consecutive_failures"] = 0
            status["last_failure_dm_at"] = now.isoformat()
        else:
            # Keep streak so we'll try again next time.
            status["last_failure_dm_at"] = status.get("last_failure_dm_at")

    _save_status(status)
    return 0


def handle_weather_ok() -> int:
    """
    Reset failure streak on a successful weather_update.
    """
    status = _load_status()
    if status.get("consecutive_failures", 0) or status.get("last_failure_dm_at"):
        status["consecutive_failures"] = 0
        # Keep last_failure_dm_at for history; we don't strictly need to clear it.
        _save_status(status)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("Usage: python -m app.src.alerts weather_fail \"reason\" | weather_ok")
        return 1

    cmd = argv[0]
    if cmd == "weather_fail":
        reason = " ".join(argv[1:]).strip() or "weather_update failed (no reason provided)."
        return handle_weather_fail(reason)
    elif cmd == "weather_ok":
        return handle_weather_ok()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python -m app.src.alerts weather_fail \"reason\" | weather_ok")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
