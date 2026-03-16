"""
app.src.notifier
----------------
Build a commute plan and optionally DM it via Discord.

Features:
- Uses planner.build_day_plan('evening'|'morning').
- Formats a compact one-line summary + detailed text block.
- Compares against data/last_plan.json and only sends when the plan
  meaningfully changes.

"Meaningful change" is based on thresholds in commute_config.toml:

[change_thresholds]
temp_change_significant          = 5    # °F
pop_change_significant           = 20   # POP percentage points (0-100)
wind_speed_change_significant    = 8    # mph
wind_gust_change_significant     = 12   # mph
clothing_change_triggers_update  = true # if false, ignore pure clothing changes

We consider changes in:
- walk_ok
- umbrella recommendation
- outerwear (if clothing_change_triggers_update is true)
- temp (>= temp_change_significant)
- POP percentage (>= pop_change_significant)
- wind speed/gust (>= wind_*_change_significant)

CLI usage:
    python -m app.src.notifier evening
    python -m app.src.notifier --dry-run evening
    python -m app.src.notifier --force evening
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import planner
from . import discord_client
from .config_loader import load_commute_config
from .logging_setup import get_logger


# --- Paths & thresholds -------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]  # /srv/2bananas/projects/commute-plan
STATE_FILE = BASE_DIR / "data" / "last_plan.json"
LOG = get_logger("notifier")


def _load_change_thresholds() -> Dict[str, Any]:
    """
    Load change detection thresholds from commute_config.toml, with defaults.
    """
    cfg = load_commute_config()
    ch = cfg.get("change_thresholds", {}) or {}

    return {
        "temp_delta_f": float(ch.get("temp_change_significant", 5.0)),
        "pop_delta_pct": float(ch.get("pop_change_significant", 20.0)),
        "wind_speed_delta": float(ch.get("wind_speed_change_significant", 8.0)),
        "wind_gust_delta": float(ch.get("wind_gust_change_significant", 12.0)),
        "clothing_change_triggers_update": bool(
            ch.get("clothing_change_triggers_update", True)
        ),
    }


# --- Helpers: plan <-> dict ---------------------------------------------------

def dayplan_to_dict(dp: planner.DayPlan) -> Dict[str, Any]:
    """
    Convert a DayPlan instance into a plain dict suitable for JSON.
    We rely on DayPlan.as_dict() if present, otherwise use dataclasses.asdict.
    """
    if hasattr(dp, "as_dict"):
        return dp.as_dict()  # type: ignore[no-any-return]
    return asdict(dp)  # type: ignore[no-any-return]


def load_last_plan() -> Optional[Dict[str, Any]]:
    """
    Load the last saved plan JSON, if it exists and is valid.
    """
    if not STATE_FILE.is_file():
        return None
    try:
        text = STATE_FILE.read_text(encoding="utf-8")
        return json.loads(text)
    except Exception:
        return None


def save_plan(plan_dict: Dict[str, Any]) -> None:
    """
    Persist the plan dict to STATE_FILE (data/last_plan.json).
    """
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(plan_dict, indent=2), encoding="utf-8")


# --- Change detection ---------------------------------------------------------

def _extract_rec_features(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a single commute recommendation dict into key features
    used for change detection.
    """
    if not rec:
        return {}

    # POP is stored as a 0–1 float; we compare in whole percentage points.
    pop_raw = rec.get("pop")
    try:
        pop_pct = int(round(float(pop_raw) * 100.0)) if pop_raw is not None else None
    except Exception:
        pop_pct = None

    # Wind (may be absent on older state files)
    def _safe_float(key: str) -> Optional[float]:
        val = rec.get(key)
        try:
            return float(val) if val is not None else None
        except Exception:
            return None

    features: Dict[str, Any] = {
        "walk_ok": bool(rec.get("walk_ok", False)),
        "umbrella": bool(rec.get("bring_umbrella", False)),
        "outerwear": rec.get("outerwear"),
        "temp": None,
        "pop_pct": pop_pct,
        "wind_speed_mph": _safe_float("wind_speed_mph"),
        "wind_gust_mph": _safe_float("wind_gust_mph"),
    }

    try:
        temp_raw = rec.get("temp")
        features["temp"] = float(temp_raw) if temp_raw is not None else None
    except Exception:
        features["temp"] = None

    return features


def _extract_key_features(plan_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce a plan dict to the bits that matter for "change":
    - For morning/afternoon: walk_ok, umbrella, outerwear, temp, POP, wind.
    """
    out: Dict[str, Any] = {"date": plan_dict.get("date")}
    for label in ("morning", "afternoon"):
        rec = plan_dict.get(label)
        out[label] = _extract_rec_features(rec) if rec else None
    return out


def compute_change_summary(
    old_plan: Optional[Dict[str, Any]],
    new_plan: Dict[str, Any],
    thresholds: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    """
    Compare old vs new plan and decide if the change is "meaningful".

    Returns:
        (changed: bool, reasons: List[str])
    """
    if thresholds is None:
        thresholds = _load_change_thresholds()

    temp_delta_f = float(thresholds.get("temp_delta_f", 5.0))
    pop_delta_pct = float(thresholds.get("pop_delta_pct", 20.0))
    wind_speed_delta = float(thresholds.get("wind_speed_delta", 8.0))
    wind_gust_delta = float(thresholds.get("wind_gust_delta", 12.0))
    clothing_triggers = bool(thresholds.get("clothing_change_triggers_update", True))

    if old_plan is None:
        return True, ["No previous plan on record; sending initial commute plan."]

    old = _extract_key_features(old_plan)
    new = _extract_key_features(new_plan)

    reasons: List[str] = []

    # Date change
    if old.get("date") != new.get("date"):
        reasons.append(f"Date changed from {old.get('date')} to {new.get('date')}.")

    for label in ("morning", "afternoon"):
        o = old.get(label)
        n = new.get(label)

        pretty_label = label.capitalize()

        if o is None and n is not None:
            reasons.append(f"{pretty_label}: new recommendation available.")
            continue
        if o is not None and n is None:
            reasons.append(f"{pretty_label}: recommendation no longer available.")
            continue
        if o is None or n is None:
            continue

        # walk_ok flip
        if o.get("walk_ok") != n.get("walk_ok"):
            reasons.append(
                f"{pretty_label}: walk_ok changed {o.get('walk_ok')} -> {n.get('walk_ok')}."
            )

        # umbrella flip
        if o.get("umbrella") != n.get("umbrella"):
            reasons.append(
                f"{pretty_label}: umbrella changed {o.get('umbrella')} -> {n.get('umbrella')}."
            )

        # outerwear change (gated by clothing_triggers)
        if clothing_triggers and o.get("outerwear") != n.get("outerwear"):
            reasons.append(
                f"{pretty_label}: outerwear changed {o.get('outerwear')} -> {n.get('outerwear')}."
            )

        # temp threshold
        try:
            old_t = float(o.get("temp")) if o.get("temp") is not None else None
            new_t = float(n.get("temp")) if n.get("temp") is not None else None
        except Exception:
            old_t = new_t = None

        if old_t is not None and new_t is not None:
            if abs(new_t - old_t) >= temp_delta_f:
                reasons.append(
                    f"{pretty_label}: temp changed {old_t:.1f}F -> {new_t:.1f}F."
                )

        # POP threshold (percentage points)
        try:
            old_pop = o.get("pop_pct")
            new_pop = n.get("pop_pct")
            if old_pop is not None and new_pop is not None:
                if abs(new_pop - old_pop) >= pop_delta_pct:
                    reasons.append(
                        f"{pretty_label}: POP changed {old_pop}% -> {new_pop}%."
                    )
        except Exception:
            pass

        # Wind speed threshold
        try:
            old_ws = o.get("wind_speed_mph")
            new_ws = n.get("wind_speed_mph")
            if (
                old_ws is not None
                and new_ws is not None
                and abs(new_ws - old_ws) >= wind_speed_delta
            ):
                reasons.append(
                    f"{pretty_label}: wind speed changed {old_ws:.1f} mph -> {new_ws:.1f} mph."
                )
        except Exception:
            pass

        # Wind gust threshold
        try:
            old_g = o.get("wind_gust_mph")
            new_g = n.get("wind_gust_mph")
            if (
                old_g is not None
                and new_g is not None
                and abs(new_g - old_g) >= wind_gust_delta
            ):
                reasons.append(
                    f"{pretty_label}: wind gust changed {old_g:.1f} mph -> {new_g:.1f} mph."
                )
        except Exception:
            pass

    return (len(reasons) > 0), reasons


# --- Formatting ---------------------------------------------------------------

def _classify_overall(plan: planner.DayPlan) -> Tuple[str, str]:
    """
    Decide emoji + short text based on walk_ok flags.

    Returns:
        (emoji, message_fragment)
    """
    m = plan.morning
    a = plan.afternoon

    m_walk = bool(m and m.walk_ok)
    a_walk = bool(a and a.walk_ok)

    if m_walk and a_walk:
        return "✅", "walking both ways looks reasonable."
    if m_walk or a_walk:
        return "⚠️", "probably walk one way and drive the other."
    return "⚠️", "probably drive or avoid walking at least one way."


def build_one_line_summary(plan: planner.DayPlan) -> str:
    """
    Build the top single-line summary:
        Tomorrow (YYYY-MM-DD): ✅ walking both ways looks reasonable.
    """
    today = date.today()
    if plan.date == today:
        label = "Today"
    elif plan.date == today + timedelta(days=1):
        label = "Tomorrow"
    else:
        label = "On " + plan.date.isoformat()

    emoji, fragment = _classify_overall(plan)
    return f"{label} ({plan.date.isoformat()}): {emoji} {fragment}"


def format_plan_block(plan: planner.DayPlan) -> str:
    """
    Build the multi-line text block shown in Discord (inside ```text).
    Mirrors the CLI format closely, including wind info if available.
    """
    lines: List[str] = []
    lines.append(f"=== Commute Plan for {plan.date.isoformat()} ===")
    lines.append("Summary:")
    if plan.summary_notes:
        for note in plan.summary_notes:
            lines.append(f"  • {note}")
    else:
        lines.append("  • (no summary notes)")

    def add_section(label: str, rec: Optional[planner.CommuteRecommendation]) -> None:
        lines.append("")
        lines.append(f"[{label}]")
        if rec is None:
            lines.append("  (no recommendation)")
            return

        lines.append(f" Leave    : {rec.leave_time_local}")
        lines.append(
            f" Temp     : {rec.temp:.1f} F (feels like {rec.feels_like:.1f} F)"
        )
        lines.append(f" POP      : {int(round(rec.pop * 100))}%")

        # Wind (may be None on older data)
        wind_speed = getattr(rec, "wind_speed_mph", None)
        wind_gust = getattr(rec, "wind_gust_mph", None)
        if wind_speed is not None:
            gust_str = f" (gusts {wind_gust:.1f} mph)" if wind_gust is not None else ""
            lines.append(f" Wind     : {wind_speed:.1f} mph{gust_str}")

        lines.append(f" Outer    : {rec.outerwear}")
        lines.append(f" Umbrella : {'yes' if rec.bring_umbrella else 'no'}")
        lines.append(f" Walk OK  : {'yes' if rec.walk_ok else 'no'}")
        for note in rec.notes:
            lines.append(f"    - {note}")

    add_section("morning", plan.morning)
    add_section("afternoon", plan.afternoon)

    return "\n".join(lines)


# --- Main flow ----------------------------------------------------------------

def build_and_maybe_send(mode: str, dry_run: bool = False, force: bool = False) -> int:
    """
    Build a plan, compare to last_plan.json, and optionally DM via Discord.

    Returns an exit code (0 = OK).
    """
    run_id = uuid.uuid4().hex[:12]
    log = LOG.bind(run_id=run_id)

    log.info(
        "notifier_start",
        mode=mode,
        dry_run=dry_run,
        force=force,
        state_file=str(STATE_FILE),
    )

    # Build new plan
    now = datetime.now()
    log.info("notifier_now", now=now.isoformat())
    plan = planner.build_day_plan(mode=mode, now=now)
    new_plan_dict = dayplan_to_dict(plan)

    # Prepare message
    one_line = build_one_line_summary(plan)
    block = format_plan_block(plan)
    message = f"{one_line}\n\n```text\n{block}\n```"

    log.info("message_preview", preview=message)

    # Load previous plan and decide if we should send
    old_plan = load_last_plan()
    thresholds = _load_change_thresholds()
    changed, reasons = compute_change_summary(old_plan, new_plan_dict, thresholds)

    if force:
        log.info("force_send_enabled")
        changed = True
        if not reasons:
            reasons = ["Forced send requested."]

    if changed:
        log.info("meaningful_change_detected")
        if reasons:
            for reason in reasons:
                log.info("change_reason", reason=reason)
    else:
        log.info("no_meaningful_change_skip_send")
        return 0

    # At this point we consider it "changed": update last_plan.json
    save_plan(new_plan_dict)
    log.info("state_saved", state_file=str(STATE_FILE))

    if dry_run:
        log.info("dry_run_skip_send")
        return 0

    # Send via discord_client
    log.info("discord_send_start")
    ok = discord_client.send_message(message)
    if ok:
        log.info("discord_send_ok")
        return 0
    else:
        log.error("discord_send_failed")
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Commute plan notifier (Discord DM).")
    parser.add_argument(
        "mode",
        nargs="?",
        default="evening",
        choices=["evening", "morning"],
        help="Plan mode: 'evening' (default) or 'morning'.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and diff plan but do not send a Discord DM.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Send even if the plan did not meaningfully change.",
    )

    args = parser.parse_args(argv)
    return build_and_maybe_send(mode=args.mode, dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
