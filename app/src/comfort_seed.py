"""
app.src.comfort_seed
--------------------
Seed helper to generate test comfort_logs rows so you can validate:
- WebUI history table + stats
- comfort_suggest output

This writes synthetic rows into data/comfort.db. It is optional and safe
to delete later.
"""

from __future__ import annotations

import argparse
import random
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Optional

from .comfort_db import ComfortLog, get_db_path, insert_comfort_log


def _ensure_column(con: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    cur = con.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    if col not in cols:
        con.execute(ddl)
        con.commit()
        print(f"[comfort_seed] Added missing column: {table}.{col}")


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _pick_wore_level(feels_like_f: float) -> int:
    """
    Rough mapping just to create plausible variety.
    You can tune these later.
    """
    if feels_like_f >= 75:
        return 1
    if feels_like_f >= 62:
        return 2
    if feels_like_f >= 52:
        return 3
    if feels_like_f >= 40:
        return 4
    return 5


def _pick_comfort(feels_like_f: float, wore_level: int, rng: random.Random) -> str:
    """
    Generate a semi-reasonable comfort label based on mismatch between
    feels-like and clothing level.
    """
    ideal = _pick_wore_level(feels_like_f)
    diff = wore_level - ideal  # + means overdressed, - means underdressed

    # baseline
    roll = rng.random()

    if diff == 0:
        # mostly comfy
        if roll < 0.65:
            return "comfortable"
        if roll < 0.85:
            return "ok"
        if roll < 0.92:
            return "a_bit_cold"
        return "a_bit_hot"

    if diff <= -2:  # much too light
        if roll < 0.55:
            return "too_cold"
        return "a_bit_cold"

    if diff == -1:  # slightly too light
        if roll < 0.55:
            return "a_bit_cold"
        if roll < 0.80:
            return "ok"
        return "comfortable"

    if diff >= 2:  # much too heavy
        if roll < 0.55:
            return "too_hot"
        return "a_bit_hot"

    # diff == +1 slightly too heavy
    if roll < 0.55:
        return "a_bit_hot"
    if roll < 0.80:
        return "ok"
    return "comfortable"


def _maybe(val: float, rng: random.Random, p: float = 0.15) -> Optional[float]:
    return None if rng.random() < p else val


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Seed comfort_logs with synthetic rows for testing.")
    ap.add_argument("--n", type=int, default=20, help="Number of rows to insert (default: 20)")
    ap.add_argument("--seed", type=int, default=1337, help="RNG seed for repeatability")
    ap.add_argument("--start-feels", type=float, default=32.0, help="Min feels-like F for generated range")
    ap.add_argument("--end-feels", type=float, default=82.0, help="Max feels-like F for generated range")
    ap.add_argument("--dry-run", action="store_true", help="Print rows that would be inserted, but do not insert")
    args = ap.parse_args(argv)

    n = _clamp_int(int(args.n), 1, 5000)
    start_f = float(args.start_feels)
    end_f = float(args.end_feels)
    if end_f < start_f:
        start_f, end_f = end_f, start_f

    rng = random.Random(int(args.seed))
    db_path = get_db_path()

    # Ensure wore_level exists (some older DBs may not have it yet)
    con = sqlite3.connect(db_path)
    try:
        _ensure_column(con, "comfort_logs", "wore_level", "ALTER TABLE comfort_logs ADD COLUMN wore_level INTEGER")
    finally:
        con.close()

    now = datetime.now().replace(microsecond=0)
    base = now - timedelta(minutes=7 * n)

    inserted = 0

    for i in range(n):
        # Spread temps across the range with a little randomness
        t = i / max(1, (n - 1))
        feels = start_f + (end_f - start_f) * t + rng.uniform(-2.5, 2.5)
        feels = round(feels, 1)

        temp = round(feels + rng.uniform(-3.0, 3.0), 1)
        lvl = _pick_wore_level(feels)

        comfort = _pick_comfort(feels, lvl, rng)

        ts_local = (base + timedelta(minutes=7 * i)).isoformat(timespec="seconds")
        leg = "morning" if (i % 2 == 0) else "afternoon"
        ctx = "commute"
        act = "walked"

        row = ComfortLog(
            timestamp_local=ts_local,
            source="seed",
            context=ctx,
            leg=leg,
            location="home",
            wore=None,
            wore_level=lvl,
            comfort=comfort,
            activity=act,
            temp_f=_maybe(temp, rng, p=0.10),
            feels_like_f=_maybe(feels, rng, p=0.05),
            wind_speed_mph=_maybe(round(rng.uniform(2.0, 25.0), 1), rng, p=0.20),
            wind_gust_mph=_maybe(round(rng.uniform(5.0, 40.0), 1), rng, p=0.25),
            humidity_pct=_maybe(round(rng.uniform(25.0, 85.0), 1), rng, p=0.20),
            pop_pct=_maybe(round(rng.uniform(0.0, 100.0), 1), rng, p=0.25),
            raw_weather_json=None,
        )

        if args.dry_run:
            print(asdict(row))
        else:
            insert_comfort_log(row, db_path=db_path)
            inserted += 1

    print("== commute-plan: comfort_seed ==")
    print(f"✅ db_path    : {db_path}")
    print(f"✅ requested  : {n}")
    print(f"✅ inserted   : {inserted if not args.dry_run else 0}")
    if args.dry_run:
        print("🟦 dry-run: no inserts performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
