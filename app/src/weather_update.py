#!/usr/bin/env python3
"""
Quick & dirty: fetch OpenWeather One Call 3.0 for Tulsa, OK and write a US-units JSON.
- Reads OPENWEATHER_API_KEY from ../secrets/.env (relative to project root).
- Fetches with units=standard, then converts to US units:
  * Temperature    K -> °F
  * Wind speed     m/s -> mph
  * Visibility     m -> miles
  * Precipitation  mm -> inches (minutely.precipitation, hourly/daily rain/snow)
  * Pressure       hPa -> inHg
Usage:
  python3 -m app.src.weather_update
  python3 app/src/weather_update.py --outfile /some/path/tulsa_weather.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from .logging_setup import get_logger

# Resolve project base dir: commute-plan/app/src -> commute-plan
HERE = Path(__file__).resolve()
BASE_DIR = HERE.parent.parent.parent  # src -> app -> commute-plan
DEFAULT_OUTFILE = BASE_DIR / "data" / "tulsa_weather.json"
LOG = get_logger("weather-update")

# --- Tulsa, OK (downtown) ---
TULSA_LAT = 36.15398
TULSA_LON = -95.99277

# ---------- unit conversions ----------
def k_to_f(k):        return round((float(k) - 273.15) * 9/5 + 32, 2)
def ms_to_mph(ms):    return round(float(ms) * 2.2369362921, 2)
def m_to_miles(m):    return round(float(m) / 1609.344, 2)
def hpa_to_inhg(hpa): return round(float(hpa) * 0.0295299830714, 2)
def mm_to_in(mm):     return round(float(mm) / 25.4, 2)

def _convert_pressure_in_place(d):
    if "pressure" in d and d["pressure"] is not None:
        d["pressure"] = hpa_to_inhg(d["pressure"])  # inHg

def _convert_wind_in_place(d):
    for k in ("wind_speed", "wind_gust"):
        if k in d and d[k] is not None:
            d[k] = ms_to_mph(d[k])  # mph

def _convert_visibility_in_place(d):
    if "visibility" in d and d["visibility"] is not None:
        d["visibility"] = m_to_miles(d["visibility"])  # miles

def _convert_temp_like_in_place(d, keys):
    for k in keys:
        if k in d and d[k] is not None:
            d[k] = k_to_f(d[k])  # °F

def _convert_rain_snow_in_place(d, field):
    if field not in d or d[field] is None:
        return
    v = d[field]
    if isinstance(v, dict):
        out = {}
        for kk, mm in v.items():
            try:
                out[f"{kk}_in"] = mm_to_in(mm)
            except Exception:
                pass
        d[field] = out
    else:
        try:
            d[field] = {"total_in": mm_to_in(v)}
        except Exception:
            pass

def _convert_feels_temp_blocks_in_place(d):
    _convert_temp_like_in_place(d, ["temp", "feels_like", "dew_point"])

def _convert_daily_temp_blocks_in_place(d):
    if "temp" in d and isinstance(d["temp"], dict):
        for k, vv in d["temp"].items():
            if vv is not None:
                d["temp"][k] = k_to_f(vv)
    if "feels_like" in d and isinstance(d["feels_like"], dict):
        for k, vv in d["feels_like"].items():
            if vv is not None:
                d["feels_like"][k] = k_to_f(vv)

def _convert_minutely_in_place(lst):
    for m in lst:
        if "precipitation" in m and m["precipitation"] is not None:
            m["precipitation"] = mm_to_in(m["precipitation"])  # inches (per minute)

def convert_payload_to_us(data: dict) -> dict:
    out = json.loads(json.dumps(data))  # deep copy
    out["_units"] = {
        "temperature": "F",
        "wind_speed": "mph",
        "visibility": "miles",
        "pressure": "inHg",
        "precip": "inches",
        "source_units": "standard",
    }

    if "current" in out and isinstance(out["current"], dict):
        c = out["current"]
        _convert_feels_temp_blocks_in_place(c)
        _convert_pressure_in_place(c)
        _convert_wind_in_place(c)
        _convert_visibility_in_place(c)
        _convert_rain_snow_in_place(c, "rain")
        _convert_rain_snow_in_place(c, "snow")

    if "hourly" in out and isinstance(out["hourly"], list):
        for h in out["hourly"]:
            _convert_feels_temp_blocks_in_place(h)
            _convert_pressure_in_place(h)
            _convert_wind_in_place(h)
            _convert_visibility_in_place(h)
            _convert_rain_snow_in_place(h, "rain")
            _convert_rain_snow_in_place(h, "snow")

    if "daily" in out and isinstance(out["daily"], list):
        for d in out["daily"]:
            _convert_daily_temp_blocks_in_place(d)
            _convert_pressure_in_place(d)
            _convert_wind_in_place(d)
            _convert_rain_snow_in_place(d, "rain")
            _convert_rain_snow_in_place(d, "snow")

    if "minutely" in out and isinstance(out["minutely"], list):
        _convert_minutely_in_place(out["minutely"])

    return out

# ---------- dotenv (no external deps) ----------
def load_env_from(path: str) -> dict:
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env

def get_api_key() -> str:
    here = os.path.abspath(os.path.dirname(__file__))
    env_path = os.path.abspath(os.path.join(here, "..", "..", "secrets", ".env"))
    env_file = load_env_from(env_path)
    return env_file.get("OPENWEATHER_API_KEY", os.getenv("OPENWEATHER_API_KEY", ""))

# ---------- fetch ----------
def fetch_raw_onecall(api_key: str, timeout: int = 20) -> dict:
    base = "https://api.openweathermap.org/data/3.0/onecall"
    url = f"{base}?lat={TULSA_LAT}&lon={TULSA_LON}&units=standard&appid={api_key}"
    req = Request(url, headers={"User-Agent": "2bananas-quickfetch/1.1"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--outfile",
        default=str(DEFAULT_OUTFILE),
        help=f"Output file path (default: {DEFAULT_OUTFILE})",
    )
    args = p.parse_args()

    api_key = get_api_key()
    if not api_key:
        LOG.error("missing_openweather_api_key")
        return 2

    try:
        raw = fetch_raw_onecall(api_key)
        us = convert_payload_to_us(raw)
        out_path = Path(args.outfile)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as f:
            json.dump(us, f, indent=2)
        LOG.info(
            "weather_saved",
            outfile=str(out_path),
            bytes=len(json.dumps(us)),
            saved_at=time.strftime('%Y-%m-%d %H:%M:%S'),
        )
        return 0
    except HTTPError as e:
        LOG.error("openweather_http_error", status=e.code, reason=str(e.reason))
        return 1
    except URLError as e:
        LOG.error("openweather_url_error", reason=str(e.reason))
        return 1
    except Exception as e:
        LOG.error("weather_update_failed", error=str(e), exc_info=True)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
