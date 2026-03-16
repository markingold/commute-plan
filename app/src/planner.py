"""
app.src.planner
---------------
Core commute-planning logic.

Responsibilities:
- Use weather_reader.list_next_hours(...) to get ~48 hours of hourly data.
- Based on config, pick the best hour for morning/afternoon commute windows
  for a target date.
- Compute clothing + umbrella + walk/drive recommendations.
- Optionally refine the **morning** departure time using minutely data
  (via weather_reader.list_next_minutes).

Wind:
- We carry through wind speed/gust from hourly data.
- Simple wind-aware rules can downgrade walk_ok and add notes based on
  configurable thresholds.

Minutely (morning mode):
- For the *morning* run only, we look at the minutely series around the chosen
  morning hour to:
    * Estimate a more up-to-the-minute "POP-style" value for that window.
    * Nudge the departure minute toward the driest part of the window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .config_loader import load_commute_config
from . import weather_reader
from .logging_setup import get_logger


LOG = get_logger("planner")


# --- Data models --------------------------------------------------------------

@dataclass
class CommuteRecommendation:
    label: str                      # "morning" | "afternoon"
    leave_time_local: datetime
    temp: float
    feels_like: float
    pop: float                      # probability of precip (0–1), possibly adjusted by minutely data
    outerwear: str                  # coat | jacket | long_sleeve | tshirt | shorts_ok
    bring_umbrella: bool
    walk_ok: bool
    notes: List[str]
    wind_speed_mph: Optional[float] = None
    wind_gust_mph: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "leave_time_local": self.leave_time_local.isoformat(),
            "temp": self.temp,
            "feels_like": self.feels_like,
            "pop": self.pop,
            "outerwear": self.outerwear,
            "bring_umbrella": self.bring_umbrella,
            "walk_ok": self.walk_ok,
            "notes": list(self.notes),
            "wind_speed_mph": self.wind_speed_mph,
            "wind_gust_mph": self.wind_gust_mph,
        }


@dataclass
class DayPlan:
    date: date
    morning: Optional[CommuteRecommendation]
    afternoon: Optional[CommuteRecommendation]
    summary_notes: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "morning": self.morning.as_dict() if self.morning else None,
            "afternoon": self.afternoon.as_dict() if self.afternoon else None,
            "summary_notes": list(self.summary_notes),
        }


# --- Basic helpers ------------------------------------------------------------

def _parse_time(hhmm: str) -> time:
    hh, mm = hhmm.split(":")
    return time(hour=int(hh), minute=int(mm))


def _compute_outerwear(feels_like_f: float, temp_cfg: Dict[str, Any]) -> str:
    """
    Map feels-like temperature to a simple clothing suggestion.
    Thresholds are configurable via [temperature_f] in commute_config.toml.
    """
    cold_coat_below = float(temp_cfg.get("cold_coat_below", 35))
    light_jacket_below = float(temp_cfg.get("light_jacket_below", 55))
    short_sleeves_above = float(temp_cfg.get("short_sleeves_above", 70))
    shorts_above = float(temp_cfg.get("shorts_above", 80))

    if feels_like_f <= cold_coat_below:
        return "coat"
    if feels_like_f <= light_jacket_below:
        return "jacket"
    if feels_like_f >= shorts_above:
        return "shorts_ok"
    if feels_like_f >= short_sleeves_above:
        return "tshirt"
    return "long_sleeve"


def _compute_precip_advice(
    pop: float,
    rain_cfg: Dict[str, Any],
) -> Tuple[bool, bool]:
    """
    Return (bring_umbrella, walk_ok) based on POP-style probability.

    Config (section [rain]):
      umbrella_pop_threshold  : % POP at/above which we bring an umbrella (default 30)
      avoid_walk_pop_threshold: % POP at/above which we prefer not to walk (default 70)
    """
    umbrella_thr = float(rain_cfg.get("umbrella_pop_threshold", 30)) / 100.0
    avoid_walk_thr = float(rain_cfg.get("avoid_walk_pop_threshold", 70)) / 100.0

    bring = pop >= umbrella_thr
    walk_ok = pop < avoid_walk_thr
    return bring, walk_ok


def _apply_wind_rules(
    feels_like_f: float,
    wind_speed_mph: Optional[float],
    wind_gust_mph: Optional[float],
    wind_cfg: Dict[str, Any],
    walk_ok: bool,
    notes: List[str],
) -> bool:
    """
    Optionally downgrade walk_ok and add notes based on wind + chill.

    Config (section [wind], all optional):
      max_steady_mph                  : if steady wind >= this, walking may be discouraged
      max_gust_mph                    : if gusts >= this, walking may be discouraged
      min_feels_like_for_windy_walk_f : if feels_like <= this AND windy, discourage walking
      breezy_note_mph                 : add a note when wind exceeds this but below hard limits
    """
    if wind_speed_mph is None and wind_gust_mph is None:
        return walk_ok

    max_steady = float(wind_cfg.get("max_steady_mph", 25.0))
    max_gust = float(wind_cfg.get("max_gust_mph", 40.0))
    chill_limit = float(wind_cfg.get("min_feels_like_for_windy_walk_f", 20.0))
    breezy_note_mph = float(wind_cfg.get("breezy_note_mph", 15.0))

    steady = wind_speed_mph or 0.0
    gust = wind_gust_mph or 0.0

    # Soft note if it's just breezy.
    if steady >= breezy_note_mph and steady < max_steady:
        notes.append(f"Breezy (around {steady:.0f} mph); consider a windproof layer.")

    # Harder limits.
    if steady >= max_steady:
        notes.append(f"Steady winds near {steady:.0f} mph; walking may be unpleasant.")
        walk_ok = False

    if gust >= max_gust:
        notes.append(f"Gusts up to ~{gust:.0f} mph; consider skipping the walk.")
        walk_ok = False

    if feels_like_f <= chill_limit and steady >= breezy_note_mph:
        notes.append("Cold and windy; wind chill may make walking uncomfortable.")
        walk_ok = False

    return walk_ok


def _score_candidate(
    feels_like_f: float,
    pop: float,
    base_dt: datetime,
    candidate_dt: datetime,
) -> float:
    """
    Score an hourly candidate for a commute window. Lower is better.

    Heuristic:
    - Strong penalty for precipitation probability.
    - Mild penalty for being far from 65F.
    - Mild penalty for being far from the nominal time.
    """
    rain_penalty = pop * 2.5  # up to ~2.5 points if pop=1.0
    comfort_penalty = abs(feels_like_f - 65.0) / 15.0
    delta_min = abs((candidate_dt - base_dt).total_seconds()) / 60.0
    time_penalty = delta_min / 60.0  # 1 point per hour offset

    return rain_penalty + comfort_penalty + time_penalty


def _pick_best_for_window(
    all_points: List[weather_reader.HourlyPoint],
    target_date: date,
    base_time_str: str,
    flex_minutes: int,
) -> Optional[weather_reader.HourlyPoint]:
    """
    Select the best HourlyPoint for a given date and time window.

    Window: base_time ± flex_minutes.
    """
    base_t = _parse_time(base_time_str)
    base_dt = datetime.combine(target_date, base_t)

    window_start = base_dt - timedelta(minutes=flex_minutes)
    window_end = base_dt + timedelta(minutes=flex_minutes)

    candidates: List[Tuple[float, weather_reader.HourlyPoint]] = []

    for p in all_points:
        dt_local = p.dt_local
        if dt_local.date() != target_date:
            continue
        if not (window_start <= dt_local <= window_end):
            continue

        score = _score_candidate(p.feels_like, p.pop, base_dt, dt_local)
        candidates.append((score, p))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


# --- Minutely refinement for morning -----------------------------------------

def _refine_departure_with_minutely(
    base_dt: datetime,
    target_date: date,
    minutely_points: List[weather_reader.MinutelyPoint],
    window_minutes: int,
) -> Tuple[datetime, Optional[float]]:
    """
    Given a base departure datetime and minutely data, choose a more precise
    departure time and estimate a POP-style value for that window.

    Strategy:
      - Consider only minutely points for the target date in
        [base_dt - window_minutes, base_dt + window_minutes].
      - Compute:
          * wet_count = minutes with precip_in > 0
          * total = minutes in window
          * pop_pct = 100 * wet_count / total
      - Choose the "best" minute as:
          * Prefer minutes with the lowest precip_in.
          * Break ties by closeness to base_dt.

    Returns:
      (best_dt_local, pop_pct or None if no minutely points used)
    """
    if not minutely_points or window_minutes <= 0:
        return base_dt, None

    window_start = base_dt - timedelta(minutes=window_minutes)
    window_end = base_dt + timedelta(minutes=window_minutes)

    window_pts: List[weather_reader.MinutelyPoint] = []
    for p in minutely_points:
        if p.dt_local.date() != target_date:
            continue
        if not (window_start <= p.dt_local <= window_end):
            continue
        window_pts.append(p)

    if not window_pts:
        return base_dt, None

    wet_count = sum(1 for p in window_pts if p.precip_in > 0.0)
    total = len(window_pts)
    pop_pct = (wet_count / total) * 100.0 if total else 0.0

    # Pick the driest minute; break ties by closeness to base_dt.
    def sort_key(p: weather_reader.MinutelyPoint) -> Tuple[float, float]:
        precip = p.precip_in
        delta_min = abs((p.dt_local - base_dt).total_seconds()) / 60.0
        return (precip, delta_min)

    best = sorted(window_pts, key=sort_key)[0]
    return best.dt_local, pop_pct


# --- Main planner entrypoint --------------------------------------------------

def _refine_morning_with_minutely(
    rec: CommuteRecommendation,
    minutely_cfg: Dict[str, Any],
    now: Optional[datetime],
) -> CommuteRecommendation:
    """Optionally nudge the morning departure time using minutely precip data.

    We look at a small window around the recommended departure time and
    choose a minute with lower precipitation if it's significantly drier,
    adding a human-friendly note if we move the time.

    All thresholds come from the optional [minutely_commute] section
    in commute_config.toml; if it is missing, sensible defaults are used.
    """
    # Feature gate: off if explicitly disabled
    if not minutely_cfg.get("enabled", True):
        return rec

    # How far around the recommended time we search, and how far ahead
    # we pull minutely data from the cached One Call payload.
    window_minutes = int(minutely_cfg.get("window_minutes", 15))
    max_minutes_ahead = int(minutely_cfg.get("max_minutes_ahead", 180))

    # Only bother mentioning a nudge if we move at least this many minutes.
    min_shift_for_note = int(minutely_cfg.get("min_shift_for_note", 3))

    # Rough precip thresholds (inches per minute) and a minimum drop
    # to consider the nudge worthwhile.
    precip_light = float(minutely_cfg.get("precip_light_in", 0.01))
    precip_heavy = float(minutely_cfg.get("precip_heavy_in", 0.03))
    min_precip_drop = float(minutely_cfg.get("min_precip_drop_in", 0.01))

    # Pull minutely points; if anything goes wrong, fall back silently.
    try:
        minutes = weather_reader.list_next_minutes(max_minutes_ahead)
    except Exception as e:  # pragma: no cover - defensive
        LOG.warning("minutely_refinement_skipped", error=str(e))
        return rec

    if not minutes:
        return rec

    from datetime import timedelta  # already imported at module level, but safe

    target = rec.leave_time_local
    window_start = target - timedelta(minutes=window_minutes)
    window_end = target + timedelta(minutes=window_minutes)

    # Restrict to a window around the recommended departure time.
    in_window = [
        p
        for p in minutes
        if window_start <= getattr(p, "dt_local", target) <= window_end
    ]
    if not in_window:
        return rec

    def _score(p):
        dt = getattr(p, "dt_local", target)
        precip = float(getattr(p, "precip_in", 0.0) or 0.0)
        # Prefer lower precip heavily, then keep close to the original time.
        time_delta_min = abs((dt - target).total_seconds()) / 60.0
        return precip * 10.0 + time_delta_min

    # Best candidate minute in the window
    best = min(in_window, key=_score)
    best_dt = getattr(best, "dt_local", target)
    best_precip = float(getattr(best, "precip_in", 0.0) or 0.0)

    # Estimate precip at the original time using the closest minutely point.
    nearest = min(
        minutes,
        key=lambda p: abs(
            (getattr(p, "dt_local", target) - target).total_seconds()
        ),
    )
    orig_precip = float(getattr(nearest, "precip_in", 0.0) or 0.0)

    shift_minutes = abs((best_dt - target).total_seconds()) / 60.0
    precip_drop = orig_precip - best_precip

    # If we're not moving much or not really improving the rain situation,
    # keep the original recommendation.
    if shift_minutes < min_shift_for_note or precip_drop < min_precip_drop:
        return rec

    # Apply the nudge and append a friendly note.
    rec.leave_time_local = best_dt
    time_str = best_dt.strftime("%H:%M")
    rec.notes.append(
        f"We nudged your morning departure to {time_str} to dodge a quick shower (minutely forecast)."
    )
    return rec

# >>> BEGIN: commute_coupling_rules >>>
def _apply_commute_coupling_rules(
    morning_rec,
    afternoon_rec,
    summary_notes,
):
    """
    Enforce car-logistics coupling:
      Allowed:  Walk AM + Walk PM
                Drive AM + Drive PM
                Drive AM + Walk PM
      Not allowed: Walk AM + Drive PM

    If the forbidden combination occurs (walk_ok AM but not walk_ok PM),
    we flip AM to drive and add a friendly note.
    Returns (morning_rec, afternoon_rec).
    """
    if not morning_rec or not afternoon_rec:
        return morning_rec, afternoon_rec

    try:
        m_ok = bool(getattr(morning_rec, "walk_ok", False))
        a_ok = bool(getattr(afternoon_rec, "walk_ok", False))
    except Exception:
        return morning_rec, afternoon_rec

    if m_ok and (not a_ok):
        # Forbidden combo: walking in would leave the car at home for a drive-home plan.
        morning_rec.walk_ok = False
        note = (
            "Walking in the morning would leave the car at home, but the afternoon "
            "doesn't look walkable—suggest driving both ways today."
        )
        try:
            if getattr(morning_rec, "notes", None) is not None:
                morning_rec.notes.append(note)
        except Exception:
            pass
        try:
            if summary_notes is not None:
                summary_notes.append(note)
        except Exception:
            pass

    return morning_rec, afternoon_rec
# <<< END: commute_coupling_rules <<<


def build_day_plan(mode: str = "evening", now: Optional[datetime] = None) -> DayPlan:
    """
    Build a DayPlan for either 'evening' (tomorrow) or 'morning' (today).

    Parameters
    ----------
    mode:
        'evening' or 'morning'
    now:
        Optional reference time; defaults to current local time.

    Returns
    -------
    DayPlan
        Plan containing morning and afternoon recommendations (if available).
    """
    if now is None:
        now = datetime.now()

    if mode == "morning":
        target_date = now.date()
    else:
        target_date = (now + timedelta(days=1)).date()

    cfg = load_commute_config()
    morning_cfg = cfg.get("morning", {})
    afternoon_cfg = cfg.get("afternoon", {})
    temp_cfg = cfg.get("temperature_f", {})
    rain_cfg = cfg.get("rain", {})
    wind_cfg = cfg.get("wind", {})

    # Hourly coverage: ~48 hours so tomorrow is fully covered from evening runs.
    points = weather_reader.list_next_hours(48)

    morning_base = str(morning_cfg.get("departure", "07:00"))
    morning_flex = int(morning_cfg.get("flex_minutes", 30))

    afternoon_base = str(afternoon_cfg.get("departure", "15:30"))
    afternoon_flex = int(afternoon_cfg.get("flex_minutes", 30))

    morning_pt = _pick_best_for_window(points, target_date, morning_base, morning_flex)
    afternoon_pt = _pick_best_for_window(points, target_date, afternoon_base, afternoon_flex)

    # Minutely is only used for morning refinement and only in the morning run.
    minutely_points: List[weather_reader.MinutelyPoint] = []
    if mode == "morning":
        # Grab up to 90 minutes of data; enough to cover typical +- flex windows.
        minutely_points = weather_reader.list_next_minutes(90)

    minutely_cfg = cfg.get("minutely", {})
    # Default: use the same flex_minutes, but cap to [5, 60] so we don't wander too far.
    default_window_min = morning_flex
    min_window = int(minutely_cfg.get("window_minutes", default_window_min))
    min_window = max(5, min(min_window, 60))

    summary_notes: List[str] = []
    morning_rec: Optional[CommuteRecommendation] = None
    afternoon_rec: Optional[CommuteRecommendation] = None

    # --- Morning recommendation ------------------------------------------------
    if morning_pt:
        effective_pop = morning_pt.pop
        leave_dt = morning_pt.dt_local
        minute_pop_pct: Optional[float] = None
        notes: List[str] = []

        # Only refine with minutely data in the morning run and when we have data.
        if mode == "morning" and minutely_points:
            refined_dt, minute_pop_pct = _refine_departure_with_minutely(
                base_dt=leave_dt,
                target_date=target_date,
                minutely_points=minutely_points,
                window_minutes=min_window,
            )
            if refined_dt != leave_dt:
                notes.append(
                    f"Departure nudged to {refined_dt.strftime('%H:%M')} "
                    f"based on minute-by-minute rain data."
                )
                leave_dt = refined_dt

            if minute_pop_pct is not None:
                # Treat minutely 'wet fraction' as another signal for POP.
                # We take the maximum of hourly POP and minutely POP-style value,
                # so we don't miss new showers that pop up.
                minute_pop = minute_pop_pct / 100.0
                effective_pop = max(effective_pop, minute_pop)
                notes.append(
                    f"Minute-level rain check: about {minute_pop_pct:.0f}% of minutes "
                    f"in your window show measurable precip."
                )

        outerwear = _compute_outerwear(morning_pt.feels_like, temp_cfg)
        bring_umbrella, walk_ok = _compute_precip_advice(effective_pop, rain_cfg)

        # Wind-aware rules
        walk_ok = _apply_wind_rules(
            feels_like_f=morning_pt.feels_like,
            wind_speed_mph=morning_pt.wind_speed_mph,
            wind_gust_mph=morning_pt.wind_gust_mph,
            wind_cfg=wind_cfg,
            walk_ok=walk_ok,
            notes=notes,
        )

        if not walk_ok and effective_pop >= float(rain_cfg.get("avoid_walk_pop_threshold", 70)) / 100.0:
            notes.append("High chance of rain; consider not walking in the morning.")

        morning_rec = CommuteRecommendation(
            label="morning",
            leave_time_local=leave_dt,
            temp=morning_pt.temp,
            feels_like=morning_pt.feels_like,
            pop=effective_pop,
            outerwear=outerwear,
            bring_umbrella=bring_umbrella,
            walk_ok=walk_ok,
            notes=notes,
            wind_speed_mph=morning_pt.wind_speed_mph,
            wind_gust_mph=morning_pt.wind_gust_mph,
        )
    else:
        summary_notes.append("No suitable morning forecast points found in the configured window.")

    # --- Afternoon recommendation ---------------------------------------------

    # Optionally refine morning departure using minutely data when running in "morning" mode.
    if mode == "morning" and morning_rec is not None:
        morning_rec = _refine_morning_with_minutely(
            morning_rec,
            minutely_cfg=cfg.get("minutely_commute", {}),
            now=now,
        )

    if afternoon_pt:
        # For afternoon we still rely on hourly POP only; minutely is not useful
        # from an evening run looking at tomorrow.
        effective_pop = afternoon_pt.pop
        notes: List[str] = []

        outerwear = _compute_outerwear(afternoon_pt.feels_like, temp_cfg)
        bring_umbrella, walk_ok = _compute_precip_advice(effective_pop, rain_cfg)

        # Wind-aware rules
        walk_ok = _apply_wind_rules(
            feels_like_f=afternoon_pt.feels_like,
            wind_speed_mph=afternoon_pt.wind_speed_mph,
            wind_gust_mph=afternoon_pt.wind_gust_mph,
            wind_cfg=wind_cfg,
            walk_ok=walk_ok,
            notes=notes,
        )

        if not walk_ok and effective_pop >= float(rain_cfg.get("avoid_walk_pop_threshold", 70)) / 100.0:
            notes.append("High chance of rain; consider not walking in the afternoon.")

        # Extra note for hot afternoons
        if afternoon_pt.feels_like >= float(temp_cfg.get("shorts_above", 80)):
            notes.append("It may be hot on the way home; consider bringing a spare shirt or shorts.")

        afternoon_rec = CommuteRecommendation(
            label="afternoon",
            leave_time_local=afternoon_pt.dt_local,
            temp=afternoon_pt.temp,
            feels_like=afternoon_pt.feels_like,
            pop=effective_pop,
            outerwear=outerwear,
            bring_umbrella=bring_umbrella,
            walk_ok=walk_ok,
            notes=notes,
            wind_speed_mph=afternoon_pt.wind_speed_mph,
            wind_gust_mph=afternoon_pt.wind_gust_mph,
        )
    else:
        summary_notes.append("No suitable afternoon forecast points found in the configured window.")

    # >>> BEGIN: apply_commute_coupling_rules >>>
    # Enforce "no Walk AM / Drive PM" car-logistics rule.
    morning_rec, afternoon_rec = _apply_commute_coupling_rules(
        morning_rec,
        afternoon_rec,
        summary_notes,
    )
    # <<< END: apply_commute_coupling_rules <<<


    # --- High-level summary ---------------------------------------------------
    if morning_rec and afternoon_rec:
        if morning_rec.walk_ok and afternoon_rec.walk_ok:
            summary_notes.append("Walking both ways looks reasonable based on current forecast.")
        elif (not morning_rec.walk_ok) and afternoon_rec.walk_ok:
            summary_notes.append(
                "Driving in and walking home looks reasonable based on current forecast."
            )
        else:
            summary_notes.append(
                "High rain or wind probabilities both ways; you may want to avoid walking."
            )
    elif morning_rec or afternoon_rec:
        rec = morning_rec or afternoon_rec
        if rec and rec.walk_ok:
            summary_notes.append("Conditions look reasonable for at least one leg of your commute.")
        else:
            summary_notes.append("Conditions do not currently look great for walking this commute.")

    return DayPlan(
        date=target_date,
        morning=morning_rec,
        afternoon=afternoon_rec,
        summary_notes=summary_notes,
    )
# ---------------------------------------------------------------------------
# Weekly overview helper (for web UI)
# ---------------------------------------------------------------------------

def _compute_walk_score_for_point(
    p: weather_reader.HourlyPoint,
    rain_cfg: Dict[str, Any],
    wind_cfg: Dict[str, Any],
) -> str:
    """Classify walkability for a single hourly point.

    Returns:
        "ok" | "caution" | "avoid"
    """
    # Precipitation-based advice
    bring_umbrella, walk_ok_precip = _compute_precip_advice(p.pop, rain_cfg)

    # Wind thresholds (may be missing on older HourlyPoint versions)
    max_speed = float(wind_cfg.get("max_walkable_speed_mph", 25.0))
    max_gust = float(wind_cfg.get("max_walkable_gust_mph", 40.0))

    wind_speed = float(getattr(p, "wind_speed_mph", 0.0))
    wind_gust = float(getattr(p, "wind_gust_mph", 0.0))

    wind_ok = (wind_speed <= max_speed) and (wind_gust <= max_gust)

    # If wind or precip clearly bad, mark as avoid.
    if not wind_ok or not walk_ok_precip:
        umbrella_thr = float(rain_cfg.get("umbrella_pop_threshold", 30)) / 100.0
        avoid_walk_thr = float(rain_cfg.get("avoid_walk_pop_threshold", 70)) / 100.0
        # Mild case: high-ish POP but below "avoid", with safe wind -> caution
        if wind_ok and umbrella_thr <= p.pop < avoid_walk_thr:
            return "caution"
        return "avoid"

    return "ok"


def _build_slot_overview(
    p: weather_reader.HourlyPoint,
    temp_cfg: Dict[str, Any],
    rain_cfg: Dict[str, Any],
    wind_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Convert a single hourly point into a compact overview dict."""
    outerwear = _compute_outerwear(p.feels_like, temp_cfg)
    walk_score = _compute_walk_score_for_point(p, rain_cfg, wind_cfg)

    return {
        "leave_time_local": p.dt_local.isoformat(),
        "temp_f": float(p.temp),
        "feels_like_f": float(p.feels_like),
        "pop": int(round(p.pop * 100)),
        "wind_speed_mph": float(getattr(p, "wind_speed_mph", 0.0)),
        "wind_gust_mph": float(getattr(p, "wind_gust_mph", 0.0)),
        "outerwear": outerwear,
        "walk_score": walk_score,
    }

def _build_slot_overview_from_daily(
    daily_point: Any,
    slot: str,
    target_date: date,
    base_time_str: str,
    temp_cfg: Dict[str, Any],
    rain_cfg: Dict[str, Any],
    wind_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Convert a daily forecast point into a compact overview dict.

    This is best-effort: different weather_reader implementations may expose
    slightly different field names. We try a few and fall back to sensible
    defaults if needed.
    """
    # --- Choose a datetime for this slot (use the configured base HH:MM) -----
    def _combine_with_time(d: date) -> datetime:
        hh, mm = base_time_str.split(":")
        return datetime(d.year, d.month, d.day, int(hh), int(mm))

    dt_attr = getattr(daily_point, "dt_local", None)
    d_attr = getattr(daily_point, "date", None)

    if isinstance(dt_attr, datetime):
        base_date = dt_attr.date()
        dt_local = _combine_with_time(base_date)
    elif isinstance(d_attr, date):
        dt_local = _combine_with_time(d_attr)
    else:
        dt_local = _combine_with_time(target_date)

    # --- Temperature: prefer slot-specific fields if present -----------------
    temp_val: Optional[float] = None
    if slot == "morning":
        cand_names = (
            "temp_morn_f",
            "temp_morn",
            "temp_min_f",
            "temp_min",
            "temp_day_f",
            "temp_day",
            "temp_max_f",
            "temp_max",
            "temp",
        )
    else:  # afternoon / PM
        cand_names = (
            "temp_day_f",
            "temp_day",
            "temp_max_f",
            "temp_max",
            "temp_min_f",
            "temp_min",
            "temp_morn_f",
            "temp_morn",
            "temp",
        )

    for name in cand_names:
        if hasattr(daily_point, name):
            val = getattr(daily_point, name)
            if val is not None:
                try:
                    temp_val = float(val)
                    break
                except (TypeError, ValueError):
                    continue

    if temp_val is None:
        temp_val = 70.0  # boring but safe default

    feels_like_f = temp_val

    # --- POP: many daily.pop fields are 0–1; accept % forms too --------------
    pop_raw = getattr(daily_point, "pop", None)
    if pop_raw is None:
        pop_raw = getattr(daily_point, "precip_prob", None)

    try:
        pop_raw_f = float(pop_raw if pop_raw is not None else 0.0)
    except (TypeError, ValueError):
        pop_raw_f = 0.0

    if pop_raw_f > 1.0:
        pop_pct = pop_raw_f
        pop_0_1 = pop_raw_f / 100.0
    else:
        pop_0_1 = pop_raw_f
        pop_pct = pop_0_1 * 100.0

    # --- Wind (if present) ----------------------------------------------------
    wind_speed = 0.0
    wind_gust = 0.0

    for name in ("wind_speed_mph", "wind_speed", "wind_spd"):
        if hasattr(daily_point, name):
            try:
                wind_speed = float(getattr(daily_point, name))
                break
            except (TypeError, ValueError):
                continue

    for name in ("wind_gust_mph", "wind_gust", "wind_gst"):
        if hasattr(daily_point, name):
            try:
                wind_gust = float(getattr(daily_point, name))
                break
            except (TypeError, ValueError):
                continue

    # --- Reuse existing walk-score logic via a tiny pseudo-hourly object -----
    class _PseudoHourly:
        __slots__ = ("dt_local", "temp", "feels_like", "pop", "wind_speed_mph", "wind_gust_mph")

        def __init__(self, dt_local, temp, feels_like, pop, wind_speed_mph, wind_gust_mph):
            self.dt_local = dt_local
            self.temp = temp
            self.feels_like = feels_like
            self.pop = pop
            self.wind_speed_mph = wind_speed_mph
            self.wind_gust_mph = wind_gust_mph

    pseudo = _PseudoHourly(
        dt_local=dt_local,
        temp=temp_val,
        feels_like=feels_like_f,
        pop=pop_0_1,
        wind_speed_mph=wind_speed,
        wind_gust_mph=wind_gust,
    )

    outerwear = _compute_outerwear(feels_like_f, temp_cfg)
    walk_score = _compute_walk_score_for_point(pseudo, rain_cfg, wind_cfg)

    return {
        "leave_time_local": dt_local.isoformat(),
        "temp_f": float(temp_val),
        "feels_like_f": float(feels_like_f),
        "pop": int(round(pop_pct)),  # 0–100, just like the hourly overview
        "wind_speed_mph": float(wind_speed),
        "wind_gust_mph": float(wind_gust),
        "outerwear": outerwear,
        "walk_score": walk_score,
    }


def build_week_overview(
    now: Optional[datetime] = None,
    days: int = 5,
) -> List[Dict[str, Any]]:
    """Build a lightweight M–F-style overview for the next few days.

    Uses hourly data where available (typically the next ~48 hours).
    For days beyond the hourly horizon, falls back to daily forecast
    if weather_reader exposes it.

    Notes:
    - If daily data is not available, later days will simply have
      morning/afternoon = None (same behavior as before).
    """
    if now is None:
        now = datetime.now()

    cfg = load_commute_config()
    morning_cfg = cfg.get("morning", {}) or {}
    afternoon_cfg = cfg.get("afternoon", {}) or {}
    temp_cfg = cfg.get("temperature_f", {}) or {}
    rain_cfg = cfg.get("rain", {}) or {}
    wind_cfg = cfg.get("wind", {}) or {}

    morning_base = str(morning_cfg.get("departure", "07:00"))
    morning_flex = int(morning_cfg.get("flex_minutes", 30))

    afternoon_base = str(afternoon_cfg.get("departure", "15:30"))
    afternoon_flex = int(afternoon_cfg.get("flex_minutes", 30))

    # Ask for enough hours to plausibly cover the requested window, but the
    # underlying JSON will clamp to what's available (often 48 hours).
    hours_ahead = max(24 * days, 48)
    points = weather_reader.list_next_hours(hours_ahead)

    # ---- Optional daily-fallback map: date -> daily_point --------------------
    daily_by_date: Dict[date, Any] = {}
    try:
        # If weather_reader doesn't implement this, the except keeps old behavior.
        daily_points: List[Any] = weather_reader.list_next_days(days)  # type: ignore[attr-defined]
    except Exception:
        # Daily data not available; fall back to hourly-only behavior
        daily_points = []

    for dp in daily_points:
        d_attr = getattr(dp, "date", None)
        dt_attr = getattr(dp, "dt_local", None)
        d_key: Optional[date] = None

        if isinstance(d_attr, date):
            d_key = d_attr
        elif isinstance(dt_attr, datetime):
            d_key = dt_attr.date()

        if d_key is not None and d_key not in daily_by_date:
            daily_by_date[d_key] = dp

    # ---- Build per-day entries ----------------------------------------------
    results: List[Dict[str, Any]] = []

    for offset in range(days):
        d = (now + timedelta(days=offset)).date()

        # 1) Try hourly-first (the existing logic)
        morning_pt = _pick_best_for_window(points, d, morning_base, morning_flex)
        afternoon_pt = _pick_best_for_window(points, d, afternoon_base, afternoon_flex)

        entry: Dict[str, Any] = {
            "date": d.isoformat(),
            "weekday": d.strftime("%a"),
            "morning": None,
            "afternoon": None,
        }

        # Morning slot
        if morning_pt is not None:
            entry["morning"] = _build_slot_overview(
                morning_pt, temp_cfg, rain_cfg, wind_cfg
            )
        elif d in daily_by_date:
            # Hourly window is empty for this date: use daily fallback.
            entry["morning"] = _build_slot_overview_from_daily(
                daily_by_date[d],
                slot="morning",
                target_date=d,
                base_time_str=morning_base,
                temp_cfg=temp_cfg,
                rain_cfg=rain_cfg,
                wind_cfg=wind_cfg,
            )

        # Afternoon slot
        if afternoon_pt is not None:
            entry["afternoon"] = _build_slot_overview(
                afternoon_pt, temp_cfg, rain_cfg, wind_cfg
            )
        elif d in daily_by_date:
            entry["afternoon"] = _build_slot_overview_from_daily(
                daily_by_date[d],
                slot="afternoon",
                target_date=d,
                base_time_str=afternoon_base,
                temp_cfg=temp_cfg,
                rain_cfg=rain_cfg,
                wind_cfg=wind_cfg,
            )

        results.append(entry)

    return results
