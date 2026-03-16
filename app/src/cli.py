"""
app.src.cli
-----------
Command-line entrypoint for the commute-plan helper.

Modes:
- test        : print basic config + paths (no Discord).
- evening     : plan for tomorrow's commutes.
- morning     : plan for today's commutes.
- weekly_json : JSON-only weekly overview for the web dashboard.

Output (evening/morning):
- A short top-line summary (one line).
- A clean multi-line text block with summary + morning/afternoon sections.
- Updates data/last_plan.json (or configured state_file).

Output (weekly_json):
- JSON to stdout with:
    {
      "generated_at": "<ISO timestamp>",
      "days": [ ... ]
    }

This CLI is used both directly and via the Smart Assistant's Discord
integration, so we keep the output friendly and free of debug noise.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config_loader import load_commute_config
from .planner import build_day_plan, DayPlan, build_week_overview
from .planner_utils import render_plan_block, render_topline
from .logging_setup import get_logger


LOG = get_logger("cli")


def _get_base_dir() -> Path:
    """
    Resolve the project base directory (.../commute-plan).
    Assumes this file lives at app/src/cli.py.
    """
    return Path(__file__).resolve().parents[2]


def _get_state_path(base_dir: Path, cfg: Dict[str, Any]) -> Path:
    """
    Resolve the path to the "last plan" state JSON.

    This is usually data/last_plan.json relative to the project base,
    but can be overridden via the 'state_file' key in commute_config.toml.
    """
    rel = cfg.get("state_file", "data/last_plan.json")
    return (base_dir / rel).resolve()


def _save_plan_json(path: Path, plan: DayPlan) -> None:
    """
    Persist a DayPlan to the given JSON path using its as_dict() helper.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = plan.as_dict()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_raw_state(path: Path) -> Dict[str, Any] | None:
    """
    Load a previously saved plan JSON if it exists and is valid.
    Currently used only for debugging / future extensions.
    """
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _print_test_info() -> None:
    """
    Print basic config + paths, but do not build a plan.
    This is handy for debugging from the shell or web UI.
    """
    base_dir = _get_base_dir()
    cfg = load_commute_config()
    state_path = _get_state_path(base_dir, cfg)
    weather_json = cfg.get("weather_json")
    LOG.info("test_mode_info", base_dir=str(base_dir), state_file=str(state_path), weather_json=str(weather_json))

    print("[commute-plan] Test mode")
    print(f"[commute-plan] Base dir     : {base_dir}")
    # Show relative path when it lives under the project root.
    rel_state = (
        state_path.relative_to(base_dir)
        if state_path.is_absolute() and str(state_path).startswith(str(base_dir))
        else state_path
    )
    print(f"[commute-plan] STATE_FILE   : {rel_state}")
    print(f"[commute-plan] WORK_DAYS    : {cfg.get('work_days')}")
    print(f"[commute-plan] Morning cfg  : {cfg.get('morning')}")
    print(f"[commute-plan] Afternoon cfg: {cfg.get('afternoon')}")
    print(f"[commute-plan] WEATHER_JSON : {weather_json}")
    print("[commute-plan] Test complete (no plan built).")


def main(argv: Optional[List[str]] = None) -> int:
    """
    CLI dispatcher.

    Modes:
      - test        : print config info, no plan.
      - evening     : build plan for tomorrow.
      - morning     : build plan for today.
      - weekly_json : JSON-only weekly overview for the web dashboard.
    """
    parser = argparse.ArgumentParser(description="Commute planner CLI")
    parser.add_argument(
        "mode",
        nargs="?",
        default="test",
        choices=["test", "evening", "morning", "weekly_json"],
        help="Mode: test | evening | morning | weekly_json (default: test)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=5,
        help="Number of days for weekly_json overview (default: 5).",
    )
    args = parser.parse_args(argv)
    run_id = uuid.uuid4().hex[:12]
    log = LOG.bind(run_id=run_id, mode=args.mode)

    # Keep weekly_json stdout pure JSON for web consumers.
    if args.mode != "weekly_json":
        log.info("cli_start", days=args.days)

    # --- Mode: test ----------------------------------------------------------
    if args.mode == "test":
        _print_test_info()
        log.info("cli_test_complete")
        return 0

    # --- Mode: weekly_json ---------------------------------------------------
    if args.mode == "weekly_json":
        # Lightweight overview structure from planner.build_week_overview().
        week = build_week_overview(now=datetime.now(), days=max(1, args.days))
        payload = {
            "generated_at": datetime.now().isoformat(),
            "days": week,
        }
        print(json.dumps(payload, indent=2))
        return 0

    # --- Modes: evening / morning -------------------------------------------
    # At this point we are in a normal "single-day" mode.
    base_dir = _get_base_dir()
    cfg = load_commute_config()
    state_path = _get_state_path(base_dir, cfg)

    # Build the plan
    plan = build_day_plan(mode=args.mode)

    # Produce user-facing text
    topline = render_topline(plan, args.mode)
    block = render_plan_block(plan)

    print(topline)
    print()
    print(block)

    # Save/refresh state JSON (for notifier to compare against)
    _save_plan_json(state_path, plan)
    log.info("cli_plan_complete", state_file=str(state_path), target_date=plan.date.isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
