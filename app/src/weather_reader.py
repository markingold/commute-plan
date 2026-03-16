"""
app.src.weather_reader
----------------------
Helpers to read the cached OpenWeather One Call 3.0 JSON for Tulsa and
extract hourly and minutely data.

Current responsibilities:
- Load JSON from the path in the WEATHER_JSON env var (or default).
- Provide helpers to list the next N hours (HourlyPoint).
- Provide helpers to list the next N minutes (MinutelyPoint) for
  up-to-the-minute commute decisions.

Notes:
- We treat the JSON written by app.src.weather_update, which already
  converts units to US-friendly values (F, mph, inches, etc.).
- Minutely data from OpenWeather 3.0 includes precipitation amount
  per minute. After our conversion step, 'precipitation' is in inches.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_WEATHER_JSON = "/srv/2bananas/projects/commute-plan/data/tulsa_weather.json"


# --- Data classes -------------------------------------------------------------

@dataclass
class HourlyPoint:
    """
    One hourly forecast point from the cached One Call JSON.
    Temperatures are in °F, wind in mph, precip in inches (where present).
    """
    dt_utc: datetime
    dt_local: datetime
    temp: float
    feels_like: float
    pop: float
    weather_code: int
    weather_desc: str
    wind_speed_mph: Optional[float] = None
    wind_gust_mph: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "dt_utc": self.dt_utc.isoformat(),
            "dt_local": self.dt_local.isoformat(),
            "temp": self.temp,
            "feels_like": self.feels_like,
            "pop": self.pop,
            "weather_code": self.weather_code,
            "weather_desc": self.weather_desc,
            "wind_speed_mph": self.wind_speed_mph,
            "wind_gust_mph": self.wind_gust_mph,
        }


@dataclass
class MinutelyPoint:
    """
    One minutely forecast point from the cached One Call JSON.

    After conversion in weather_update.py, 'precipitation' is stored
    in inches per minute for this point.
    """
    dt_utc: datetime
    dt_local: datetime
    precip_in: float  # inches of precip in this minute

    def as_dict(self) -> Dict[str, Any]:
        return {
            "dt_utc": self.dt_utc.isoformat(),
            "dt_local": self.dt_local.isoformat(),
            "precip_in": self.precip_in,
        }


# --- Path resolution ----------------------------------------------------------

def _get_weather_path() -> Path:
    """
    Resolve the path to the cached weather JSON file from environment,
    falling back to a hard-coded default.
    """
    env_path = os.getenv("WEATHER_JSON", "").strip()
    if env_path:
        return Path(env_path)
    return Path(DEFAULT_WEATHER_JSON)


def load_weather_json(path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load the cached OpenWeather JSON from disk.

    Raises FileNotFoundError if the file is missing,
    or json.JSONDecodeError if the file is invalid.
    """
    path = path or _get_weather_path()
    if not path.is_file():
        raise FileNotFoundError(f"Weather JSON not found: {path}")

    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    return data


# --- Time helpers -------------------------------------------------------------

def _to_local_time(dt_utc: datetime, tz_offset_seconds: int) -> datetime:
    """
    Convert a UTC datetime to *naive* local time using the timezone offset from
    the API (in seconds). This is sufficient for our commute use case.

    Note: we intentionally return a naive datetime for simple comparisons
    against other naive datetimes in the planner.
    """
    return (dt_utc + timedelta(seconds=tz_offset_seconds)).replace(tzinfo=None)


# --- Hourly helpers -----------------------------------------------------------

def list_next_hours(count: int = 8, path: Optional[Path] = None) -> List[HourlyPoint]:
    """
    Return the next `count` hours of forecast as HourlyPoint objects.

    This is primarily for debugging and sanity checks, and is also used
    by the planner to pick commute windows.
    """
    data = load_weather_json(path)
    hourly = data.get("hourly") or []
    tz_offset = int(data.get("timezone_offset", 0))

    points: List[HourlyPoint] = []
    for entry in hourly[:count]:
        ts = int(entry.get("dt"))
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        dt_local = _to_local_time(dt_utc, tz_offset)
        weather_list = entry.get("weather") or [{}]
        weather = weather_list[0] or {}

        wind_speed = entry.get("wind_speed")
        wind_gust = entry.get("wind_gust")

        points.append(
            HourlyPoint(
                dt_utc=dt_utc,
                dt_local=dt_local,
                temp=float(entry.get("temp")),
                feels_like=float(entry.get("feels_like")),
                pop=float(entry.get("pop", 0.0)),
                weather_code=int(weather.get("id", 0)),
                weather_desc=str(weather.get("description", "")),
                wind_speed_mph=float(wind_speed) if wind_speed is not None else None,
                wind_gust_mph=float(wind_gust) if wind_gust is not None else None,
            )
        )
    return points


# --- Minutely helpers ---------------------------------------------------------

def list_next_minutes(count: int = 60, path: Optional[Path] = None) -> List[MinutelyPoint]:
    """
    Return the next `count` minutes of forecast as MinutelyPoint objects.

    Assumes the JSON has been pre-converted by weather_update.py so that
    'minutely[].precipitation' is expressed in inches.
    """
    data = load_weather_json(path)
    minutely = data.get("minutely") or []
    tz_offset = int(data.get("timezone_offset", 0))

    points: List[MinutelyPoint] = []
    for entry in minutely[:count]:
        ts = int(entry.get("dt"))
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        dt_local = _to_local_time(dt_utc, tz_offset)
        precip_in = float(entry.get("precipitation", 0.0))

        points.append(
            MinutelyPoint(
                dt_utc=dt_utc,
                dt_local=dt_local,
                precip_in=precip_in,
            )
        )
    return points

# --- Daily helpers -------------------------------------------------------------

@dataclass
class DailyPoint:
    """
    One daily forecast point from the cached One Call JSON.

    Temperatures are in °F (via weather_update.convert_payload_to_us),
    wind in mph, POP as 0–1 fraction, and date reflects local time.
    """
    dt_utc: datetime
    dt_local: datetime
    date: date
    pop: float
    temp_morn_f: Optional[float] = None
    temp_day_f: Optional[float] = None
    temp_eve_f: Optional[float] = None
    temp_night_f: Optional[float] = None
    temp_min_f: Optional[float] = None
    temp_max_f: Optional[float] = None
    wind_speed_mph: Optional[float] = None
    wind_gust_mph: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "dt_utc": self.dt_utc.isoformat(),
            "dt_local": self.dt_local.isoformat(),
            "date": self.date.isoformat(),
            "pop": self.pop,
            "temp_morn_f": self.temp_morn_f,
            "temp_day_f": self.temp_day_f,
            "temp_eve_f": self.temp_eve_f,
            "temp_night_f": self.temp_night_f,
            "temp_min_f": self.temp_min_f,
            "temp_max_f": self.temp_max_f,
            "wind_speed_mph": self.wind_speed_mph,
            "wind_gust_mph": self.wind_gust_mph,
        }


def list_next_days(count: int = 7, path: Optional[Path] = None) -> List[DailyPoint]:
    """
    Return the next `count` days of forecast as DailyPoint objects.

    This uses the converted One Call payload written by weather_update.py,
    which already expresses:
      - daily[].temp[day/min/max/morn/eve/night] in °F
      - wind_speed / wind_gust in mph
      - pop as a 0–1 probability (or 0–100 % on some providers).
    """
    data = load_weather_json(path)
    daily = data.get("daily") or []
    tz_offset = int(data.get("timezone_offset", 0))

    points: List[DailyPoint] = []
    for entry in daily[:count]:
        try:
            ts = int(entry.get("dt"))
        except Exception:
            # Skip malformed entries
            continue

        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        dt_local = _to_local_time(dt_utc, tz_offset)
        d = dt_local.date()

        temp_block = entry.get("temp") or {}
        temp_morn = temp_block.get("morn")
        temp_day = temp_block.get("day")
        temp_eve = temp_block.get("eve")
        temp_night = temp_block.get("night")
        temp_min = temp_block.get("min")
        temp_max = temp_block.get("max")

        pop_raw = entry.get("pop", 0.0)
        try:
            pop_val = float(pop_raw)
        except (TypeError, ValueError):
            pop_val = 0.0

        wind_speed = entry.get("wind_speed")
        wind_gust = entry.get("wind_gust")

        points.append(
            DailyPoint(
                dt_utc=dt_utc,
                dt_local=dt_local,
                date=d,
                pop=pop_val,
                temp_morn_f=float(temp_morn) if temp_morn is not None else None,
                temp_day_f=float(temp_day) if temp_day is not None else None,
                temp_eve_f=float(temp_eve) if temp_eve is not None else None,
                temp_night_f=float(temp_night) if temp_night is not None else None,
                temp_min_f=float(temp_min) if temp_min is not None else None,
                temp_max_f=float(temp_max) if temp_max is not None else None,
                wind_speed_mph=float(wind_speed) if wind_speed is not None else None,
                wind_gust_mph=float(wind_gust) if wind_gust is not None else None,
            )
        )

    return points
