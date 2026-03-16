"""
app.src.comfort_cli
-------------------
CLI for logging "comfort feedback" rows into data/comfort.db.

Goal: be callable from anywhere (web UI / Discord / CLI) and consistently
capture the closest hourly weather point from the cached tulsa_weather.json.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .comfort_db import ComfortLog, get_db_path, insert_comfort_log, wear_level_desc
from .weather_reader import load_weather_json


def _parse_timestamp_local(raw: str) -> datetime:
    raw = (raw or "").strip().lower()
    if raw in ("", "now", "today"):
        return datetime.now()
    # accept "YYYY-MM-DD HH:MM" by converting to ISO-ish
    if " " in raw and "t" not in raw:
        raw = raw.replace(" ", "T")
    # allow seconds optional
    return datetime.fromisoformat(raw)


def _to_local_time(dt_utc: datetime, tz_offset_seconds: int) -> datetime:
    return (dt_utc + timedelta(seconds=tz_offset_seconds)).replace(tzinfo=None)


def _find_nearest_hourly(data: Dict[str, Any], target_local: datetime) -> Tuple[Optional[Dict[str, Any]], Optional[datetime]]:
    """
    Find the hourly[] entry whose local time is nearest to target_local.
    Returns (entry, entry_dt_local) or (None, None).
    """
    hourly = data.get("hourly") or []
    tz_offset = int(data.get("timezone_offset", 0))
    best = None
    best_local = None
    best_abs = None

    for entry in hourly:
        try:
            ts = int(entry.get("dt"))
        except Exception:
            continue
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        dt_local = _to_local_time(dt_utc, tz_offset)
        delta = abs((dt_local - target_local).total_seconds())

        if best_abs is None or delta < best_abs:
            best_abs = delta
            best = entry
            best_local = dt_local

    return best, best_local


def _pop_to_pct(pop_raw: Any) -> Optional[float]:
    if pop_raw is None:
        return None
    try:
        v = float(pop_raw)
    except Exception:
        return None
    # OpenWeather hourly pop is usually 0..1. Some conversions might make it 0..100.
    if v <= 1.0:
        return round(v * 100.0, 2)
    return round(v, 2)


def _extract_weather_fields(hourly_entry: Dict[str, Any]) -> Dict[str, Any]:
    # These keys match what weather_update writes (US units).
    out: Dict[str, Any] = {}

    def f(key: str) -> Optional[float]:
        v = hourly_entry.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

    out["temp_f"] = f("temp")
    out["feels_like_f"] = f("feels_like")
    out["wind_speed_mph"] = f("wind_speed")
    out["wind_gust_mph"] = f("wind_gust")

    h = hourly_entry.get("humidity")
    try:
        out["humidity_pct"] = float(h) if h is not None else None
    except Exception:
        out["humidity_pct"] = None

    out["pop_pct"] = _pop_to_pct(hourly_entry.get("pop"))

    # keep a compact raw blob for later analysis/debugging
    out["raw_weather_json"] = json.dumps(hourly_entry, separators=(",", ":"), ensure_ascii=False)

    return out


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Log comfort feedback into comfort.db")
    p.add_argument("--timestamp-local", default="now", help="Local timestamp (ISO) or 'now' (default).")
    p.add_argument("--source", default="cli", help="Source tag (cli|web|discord|...)")
    p.add_argument("--context", default="commute", help="Context (commute|laps|errand|...)")
    p.add_argument("--leg", default="", help="Leg (morning|afternoon|lunch|...) optional")
    p.add_argument("--location", default="", help="Location label optional")
    p.add_argument("--wore", default="", help="What you wore (free text / small taxonomy)")
    p.add_argument("--wore-level", type=int, default=0, help="Wear level 1-5 (optional). 1=short sleeve, 5=full winter kit")
    p.add_argument("--comfort", default="", help="Comfort (ok|too_cold|too_hot|...)")
    p.add_argument("--activity", default="", help="Activity (walked|drove|laps|...)")

    p.add_argument("--dry-run", action="store_true", help="Do not insert; print what would be inserted.")
    args = p.parse_args(argv)

    target_local = _parse_timestamp_local(args.timestamp_local)

    data = load_weather_json()
    entry, entry_local = _find_nearest_hourly(data, target_local)

    weather_fields: Dict[str, Any] = {}
    if entry is not None:
        weather_fields = _extract_weather_fields(entry)

    row = ComfortLog(
        timestamp_local=target_local.isoformat(timespec="seconds"),
        source=(args.source or "cli").strip() or "cli",
        context=(args.context or "commute").strip() or "commute",
        leg=(args.leg.strip() or None),
        location=(args.location.strip() or None),
        wore=(args.wore.strip() or None),
        wore_level=(int(args.wore_level) if int(args.wore_level or 0) in (1,2,3,4,5) else None),
        comfort=(args.comfort.strip() or None),
        activity=(args.activity.strip() or None),
        temp_f=weather_fields.get("temp_f"),
        feels_like_f=weather_fields.get("feels_like_f"),
        wind_speed_mph=weather_fields.get("wind_speed_mph"),
        wind_gust_mph=weather_fields.get("wind_gust_mph"),
        humidity_pct=weather_fields.get("humidity_pct"),
        pop_pct=weather_fields.get("pop_pct"),
        raw_weather_json=weather_fields.get("raw_weather_json"),
    )

    print("== commute-plan comfort logger ==")
    print(f"✅ timestamp_local : {row.timestamp_local}")
    print(f"✅ source/context  : {row.source} / {row.context}")
    if row.leg: print(f"✅ leg            : {row.leg}")
    if row.location: print(f"✅ location       : {row.location}")
    if row.activity: print(f"✅ activity       : {row.activity}")
    if row.wore: print(f"✅ wore           : {row.wore}")
    if row.wore_level: print(f"✅ wore_level     : {row.wore_level} ({wear_level_desc(row.wore_level)})")
    if row.comfort: print(f"✅ comfort        : {row.comfort}")

    if entry is None:
        print("⚠️  No hourly weather entry found; storing feedback without weather fields.")
    else:
        when = entry_local.isoformat(timespec="minutes") if entry_local else "?"
        print(f"✅ nearest hourly : {when}")
        print(f"✅ weather        : temp={row.temp_f}F feels={row.feels_like_f}F pop={row.pop_pct}% wind={row.wind_speed_mph} gust={row.wind_gust_mph} humidity={row.humidity_pct}")

    if args.dry_run:
        print("🟦 dry-run: not inserting into DB")
        return 0

    db_path = get_db_path()
    new_id = insert_comfort_log(row, db_path=db_path)
    print(f"✅ inserted id    : {new_id}")
    print(f"✅ db_path        : {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
