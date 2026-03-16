"""
app.src.planner_utils
---------------------
Helpers for:
- Rendering a DayPlan as a short "top line" summary.
- Rendering a readable multi-line text block for terminal / Discord.

These are used by:
- app.src.cli (manual runs / !commute commands)
- app.src.notifier (cron-based Discord notifications)
"""

from __future__ import annotations

from typing import List

from .planner import DayPlan, CommuteRecommendation


def _format_rec_block(label: str, rec: CommuteRecommendation) -> List[str]:
    """
    Render a single CommuteRecommendation into lines for display.
    """
    lines: List[str] = []
    lines.append(f"[{label}]")
    lines.append(f"  Leave local : {rec.leave_time_local}")
    lines.append(f"  Temp        : {rec.temp:.1f} F (feels like {rec.feels_like:.1f} F)")
    lines.append(f"  POP         : {int(round(rec.pop * 100))}%")

    # Wind is optional; only render if we have a value.
    if rec.wind_speed_mph is not None:
        if rec.wind_gust_mph is not None:
            lines.append(
                f"  Wind        : {rec.wind_speed_mph:.1f} mph "
                f"(gusts {rec.wind_gust_mph:.1f} mph)"
            )
        else:
            lines.append(f"  Wind        : {rec.wind_speed_mph:.1f} mph")

    lines.append(f"  Outerwear   : {rec.outerwear}")
    lines.append(f"  Umbrella    : {'yes' if rec.bring_umbrella else 'no'}")
    lines.append(f"  Walk OK     : {'yes' if rec.walk_ok else 'no'}")

    if rec.notes:
        lines.append("  Notes       :")
        for n in rec.notes:
            lines.append(f"    - {n}")
    return lines


def render_plan_block(plan: DayPlan) -> str:
    """
    Render a DayPlan as a readable multi-line text block without internal
    debug lines. Suitable for both terminal and Discord code blocks.
    """
    lines: List[str] = []

    lines.append(f"=== Commute Plan for {plan.date.isoformat()} ===")

    if plan.summary_notes:
        lines.append("Summary:")
        for note in plan.summary_notes:
            lines.append(f"  • {note}")
        lines.append("")

    if plan.morning:
        lines.extend(_format_rec_block("morning", plan.morning))
        lines.append("")

    if plan.afternoon:
        lines.extend(_format_rec_block("afternoon", plan.afternoon))
        lines.append("")

    if not plan.morning and not plan.afternoon:
        lines.append("No commute recommendations available for the selected date.")

    # Strip trailing blank lines for a clean ending
    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines)


def render_topline(plan: DayPlan, mode: str) -> str:
    """
    Render a super-short one-line human summary, e.g.:

    - "Tomorrow (2025-11-17): ✅ walking both ways looks reasonable."
    - "Today (2025-11-16): ⚠️ walking one way looks ok; be cautious for the other."
    - "Tomorrow (2025-11-17): 🚫 probably drive both ways or avoid walking."
    """
    label = "Today" if mode == "morning" else "Tomorrow"

    m = plan.morning
    a = plan.afternoon

    if m and a:
        if m.walk_ok and a.walk_ok:
            mood = "✅ walking both ways looks reasonable."
        elif (not m.walk_ok) and a.walk_ok:
            mood = "⚠️ drive in, walking home looks ok based on the forecast."
        else:
            mood = "🚫 probably drive both ways or avoid walking."
    elif m or a:
        rec = m or a
        if rec.walk_ok:
            mood = "✅ walking is reasonable based on the forecast."
        else:
            mood = "🚫 probably avoid walking based on the forecast."
    else:
        mood = "⚠️ no suitable forecast points for your commute windows."

    return f"{label} ({plan.date.isoformat()}): {mood}"
