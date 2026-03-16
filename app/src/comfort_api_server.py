"""
app.src.comfort_api_server
-------------------------
Tiny stdlib HTTP server to accept comfort log inserts via JSON.

Endpoints:
  GET  /health
  POST /comfort-log

POST body example:
{
  "timestamp_local": "2025-12-12T08:05:00",
  "source": "discord",
  "context": "morning_commute",
  "leg": "am",
  "location": "home",
  "wore": "hoodie",
  "wore_level": 3,
  "comfort": "a_bit_cold",
  "activity": "walking"
}

Returns:
{
  "ok": true,
  "id": 123,
  "nearest_hourly_local": "2025-12-12T08:00",
  "temp_f": 64.0,
  ...
}
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple

from .comfort_db import ComfortLog, get_db_path, insert_comfort_log
from .weather_reader import load_weather_json
from .logging_setup import get_logger


# -----------------------------------------------------------------------------
# Helpers (kept local to avoid touching existing CLI/bot code)
# -----------------------------------------------------------------------------

LOG = get_logger("comfort-api")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
START_MONO = time.monotonic()

def _parse_timestamp_local(raw: str) -> datetime:
    raw = (raw or "").strip()
    if raw == "" or raw.lower() in ("now", "today"):
        return datetime.now()
    if " " in raw and "t" not in raw.lower():
        raw = raw.replace(" ", "T")
    return datetime.fromisoformat(raw)


def _to_local_time(dt_utc: datetime, tz_offset_seconds: int) -> datetime:
    return (dt_utc + timedelta(seconds=tz_offset_seconds)).replace(tzinfo=None)


def _find_nearest_hourly(data: Dict[str, Any], target_local: datetime) -> Tuple[Optional[Dict[str, Any]], Optional[datetime]]:
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
    if v <= 1.0:
        return round(v * 100.0, 2)
    return round(v, 2)


def _extract_weather_fields(hourly_entry: Dict[str, Any]) -> Dict[str, Any]:
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
    out["raw_weather_json"] = json.dumps(hourly_entry, separators=(",", ":"), ensure_ascii=False)
    return out


def _norm(s: Any) -> str:
    return ("" if s is None else str(s)).strip()


def _parse_wore_level(v: Any) -> Optional[int]:
    s = _norm(v).lower()
    if s == "":
        return None
    # allow shorthand like "lvl3", "level4", "l2"
    for pfx in ("lvl", "level", "l"):
        if s.startswith(pfx) and s[len(pfx):].isdigit():
            s = s[len(pfx):]
            break
    try:
        n = int(s)
    except Exception:
        return None
    return n if n in (1, 2, 3, 4, 5) else None


def _ensure_column(con: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    cur = con.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    if col not in cols:
        con.execute(ddl)
        con.commit()
        LOG.info("db_column_added", table=table, column=col)


# -----------------------------------------------------------------------------
# HTTP handler
# -----------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "commute-plan-comfort/1.0"

    def _request_id(self) -> str:
        incoming = (self.headers.get("X-Request-Id") or "").strip()
        if incoming:
            return incoming[:128]
        return uuid.uuid4().hex

    def _send_json(self, code: int, payload: Dict[str, Any], request_id: Optional[str] = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if request_id:
            self.send_header("X-Request-Id", request_id)
        # permissive CORS so Nova/other clients can post easily (local use)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        request_id = self._request_id()
        self.send_response(204)
        self.send_header("X-Request-Id", request_id)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

        LOG.info(
            "http_request",
            request_id=request_id,
            method="OPTIONS",
            path=self.path,
            status=204,
            duration_ms=0,
        )

    def do_GET(self) -> None:
        t0 = time.perf_counter()
        request_id = self._request_id()
        if self.path.rstrip("/") == "/health":
            payload = {
                "ok": True,
                "service": "comfort_api",
                "version": APP_VERSION,
                "time": datetime.now(timezone.utc).isoformat(),
                "uptime_s": round(time.monotonic() - START_MONO, 3),
            }
            self._send_json(200, payload, request_id=request_id)
            LOG.info(
                "http_request",
                request_id=request_id,
                method="GET",
                path=self.path,
                status=200,
                duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            )
            return
        if self.path.rstrip("/") == "/version":
            self._send_json(200, {"ok": True, "version": APP_VERSION}, request_id=request_id)
            LOG.info(
                "http_request",
                request_id=request_id,
                method="GET",
                path=self.path,
                status=200,
                duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            )
            return

        self._send_json(404, {"ok": False, "error": "not_found"}, request_id=request_id)
        LOG.info(
            "http_request",
            request_id=request_id,
            method="GET",
            path=self.path,
            status=404,
            duration_ms=round((time.perf_counter() - t0) * 1000, 2),
        )

    def do_POST(self) -> None:
        t0 = time.perf_counter()
        request_id = self._request_id()
        if self.path.rstrip("/") != "/comfort-log":
            self._send_json(404, {"ok": False, "error": "not_found"}, request_id=request_id)
            LOG.info(
                "http_request",
                request_id=request_id,
                method="POST",
                path=self.path,
                status=404,
                duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            )
            return

        try:
            n = int(self.headers.get("Content-Length") or "0")
        except Exception:
            n = 0
        raw = self.rfile.read(n) if n > 0 else b"{}"

        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON must be an object")
        except Exception as e:
            self._send_json(400, {"ok": False, "error": "bad_json", "detail": str(e)}, request_id=request_id)
            LOG.warning(
                "http_request",
                request_id=request_id,
                method="POST",
                path=self.path,
                status=400,
                duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                error="bad_json",
            )
            return

        # Parse inputs
        try:
            ts_local = _parse_timestamp_local(_norm(data.get("timestamp_local") or "now"))
        except Exception as e:
            self._send_json(400, {"ok": False, "error": "bad_timestamp_local", "detail": str(e)}, request_id=request_id)
            LOG.warning(
                "http_request",
                request_id=request_id,
                method="POST",
                path=self.path,
                status=400,
                duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                error="bad_timestamp_local",
            )
            return

        source = _norm(data.get("source") or "api") or "api"
        context = _norm(data.get("context") or "commute") or "commute"
        leg = _norm(data.get("leg"))
        location = _norm(data.get("location"))
        wore = _norm(data.get("wore"))
        comfort = _norm(data.get("comfort"))
        activity = _norm(data.get("activity"))

        wore_level = _parse_wore_level(data.get("wore_level"))

        # Weather snapshot
        hourly = None
        hourly_local = None
        weather_fields: Dict[str, Any] = {}
        try:
            wx = load_weather_json()
            hourly, hourly_local = _find_nearest_hourly(wx, ts_local)
            if hourly is not None:
                weather_fields = _extract_weather_fields(hourly)
        except Exception:
            # don't fail logging if weather cache is missing
            hourly = None
            hourly_local = None
            weather_fields = {}

        row = ComfortLog(
            timestamp_local=ts_local.isoformat(timespec="seconds"),
            source=source,
            context=context,
            leg=(leg or None),
            location=(location or None),
            wore=(wore or None),
            wore_level=wore_level,
            comfort=(comfort or None),
            activity=(activity or None),
            temp_f=weather_fields.get("temp_f"),
            feels_like_f=weather_fields.get("feels_like_f"),
            wind_speed_mph=weather_fields.get("wind_speed_mph"),
            wind_gust_mph=weather_fields.get("wind_gust_mph"),
            humidity_pct=weather_fields.get("humidity_pct"),
            pop_pct=weather_fields.get("pop_pct"),
            raw_weather_json=weather_fields.get("raw_weather_json"),
        )

        db_path = get_db_path()

        # Ensure wore_level column exists (older DBs)
        con = sqlite3.connect(db_path)
        try:
            _ensure_column(con, "comfort_logs", "wore_level", "ALTER TABLE comfort_logs ADD COLUMN wore_level INTEGER")
        finally:
            con.close()

        try:
            new_id = insert_comfort_log(row, db_path=db_path)
        except Exception as e:
            self._send_json(500, {"ok": False, "error": "db_insert_failed", "detail": str(e)}, request_id=request_id)
            LOG.error(
                "http_request",
                request_id=request_id,
                method="POST",
                path=self.path,
                status=500,
                duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                error="db_insert_failed",
            )
            return

        resp: Dict[str, Any] = {"ok": True, "id": new_id}
        if hourly_local is not None:
            resp["nearest_hourly_local"] = hourly_local.isoformat(timespec="minutes")
        resp.update(
            {k: row.__dict__.get(k) for k in (
                "temp_f","feels_like_f","wind_speed_mph","wind_gust_mph","humidity_pct","pop_pct","wore_level"
            )}
        )
        self._send_json(200, resp, request_id=request_id)
        LOG.info(
            "http_request",
            request_id=request_id,
            method="POST",
            path=self.path,
            status=200,
            duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            row_id=new_id,
        )


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Commute-plan comfort log HTTP server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8099)
    args = ap.parse_args(argv)

    httpd = ThreadingHTTPServer((args.host, int(args.port)), Handler)
    LOG.info("server_start", host=args.host, port=args.port, version=APP_VERSION)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
