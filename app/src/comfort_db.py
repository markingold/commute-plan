"""
app.src.comfort_db
------------------
Tiny SQLite helper for recording "comfort feedback" rows into data/comfort.db.

This is intentionally small and dependency-free so it can be used by:
- Discord command handlers (later)
- Web UI (PHP shell_exec calling Python)
- CLI tools
"""

from __future__ import annotations



# >>> BEGIN: wear_levels >>>
WEAR_LEVELS = {
    1: "short sleeve shirt (no jacket)",
    2: "long sleeve shirt",
    3: "long sleeve + undershirt",
    4: "long sleeve + undershirt + jacket/coat",
    5: "coat + gloves + winter hat + scarf",
}

def wear_level_desc(level: int | None) -> str:
    if not level:
        return ""
    try:
        return WEAR_LEVELS.get(int(level), "")
    except Exception:
        return ""
# <<< END: wear_levels <<<
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _get_base_dir() -> Path:
    # .../commute-plan (assumes this file is app/src/comfort_db.py)
    return Path(__file__).resolve().parents[2]


def get_db_path() -> Path:
    """
    Resolve comfort DB path.
    - COMFORT_DB env var can override.
    - Default: <project>/data/comfort.db
    """
    env = (os.getenv("COMFORT_DB") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (_get_base_dir() / "data/comfort.db").resolve()


@dataclass
class ComfortLog:
    timestamp_local: str
    source: str
    context: str
    leg: Optional[str] = None
    location: Optional[str] = None
    wore: Optional[str] = None
    wore_level: Optional[int] = None
    comfort: Optional[str] = None
    activity: Optional[str] = None
    temp_f: Optional[float] = None
    feels_like_f: Optional[float] = None
    wind_speed_mph: Optional[float] = None
    wind_gust_mph: Optional[float] = None
    humidity_pct: Optional[float] = None
    pop_pct: Optional[float] = None
    raw_weather_json: Optional[str] = None

    def as_db_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_local": self.timestamp_local,
            "source": self.source,
            "context": self.context,
            "leg": self.leg,
            "location": self.location,
            "wore": self.wore,
            "wore_level": self.wore_level,
            "comfort": self.comfort,
            "activity": self.activity,
            "temp_f": self.temp_f,
            "feels_like_f": self.feels_like_f,
            "wind_speed_mph": self.wind_speed_mph,
            "wind_gust_mph": self.wind_gust_mph,
            "humidity_pct": self.humidity_pct,
            "pop_pct": self.pop_pct,
            "raw_weather_json": self.raw_weather_json,
        }




# >>> BEGIN: ensure_wore_level_column >>>
def ensure_wore_level_column(conn) -> None:
    """Add wore_level column if missing (safe, idempotent)."""
    try:
        cur = conn.execute("PRAGMA table_info(comfort_logs)")
        cols = {r[1] for r in cur.fetchall() if len(r) > 1}
        if "wore_level" not in cols:
            conn.execute("ALTER TABLE comfort_logs ADD COLUMN wore_level INTEGER")
            conn.commit()
    except Exception:
        # Never block inserts due to a migration attempt; caller may still succeed.
        pass
# <<< END: ensure_wore_level_column <<<

def insert_comfort_log(row: ComfortLog, db_path: Optional[Path] = None) -> int:
    """
    Insert a ComfortLog row into comfort_logs. Returns inserted row id.
    """
    db_path = db_path or get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    sql = """
    INSERT INTO comfort_logs (
      timestamp_local, source, context, leg, location, wore, comfort, activity,
      temp_f, feels_like_f, wind_speed_mph, wind_gust_mph, humidity_pct, pop_pct,
      raw_weather_json
    ) VALUES (
      :timestamp_local, :source, :context, :leg, :location, :wore, :comfort, :activity,
      :temp_f, :feels_like_f, :wind_speed_mph, :wind_gust_mph, :humidity_pct, :pop_pct,
      :raw_weather_json
    )
    """
    params = row.as_db_dict()

    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute(sql, params)
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()
