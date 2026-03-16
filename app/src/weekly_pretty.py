import sys
import json
from typing import Any, Dict, Optional


def emoji_for_outerwear(outerwear: Optional[str]) -> str:
    """
    Map the planner's 'outerwear' string to a clothing emoji.
    Known examples from your data: 'jacket', 'tshirt', 'long_sleeve'.
    We also handle future values like 'heavy_coat', 'shorts', etc.
    """
    if not outerwear:
        return "👕"  # safe default

    o = outerwear.lower()

    # Heavier layers
    if "heavy" in o or "coat" in o:
        return "🧥"
    if "jacket" in o:
        return "🧶"

    # Long sleeves
    if "long" in o:
        return "👕"  # could be long-sleeve tee

    # Shorts explicitly
    if "shorts" in o:
        return "🩳👕"

    # T-shirt / short sleeve
    if "tshirt" in o or "t-shirt" in o or "short_sleeve" in o:
        return "👕"

    # Fallback
    return "👕"


def emoji_for_walk_score(score: Optional[str]) -> str:
    """
    Map the planner's 'walk_score' string to a walkability emoji.
    Known example: 'ok'.
    We'll assume:
      - 'ok' / 'good' / 'great' / 'yes' => ✅
      - 'maybe' / 'borderline' / 'mixed' => ⚠️
      - 'avoid' / 'bad' / 'no' => 🚫
    """
    if not score:
        return "⚠️"

    s = score.lower()

    if s in {"ok", "good", "great", "yes"}:
        return "✅"
    if s in {"maybe", "borderline", "mixed"}:
        return "⚠️"
    if s in {"avoid", "bad", "no"}:
        return "🚫"

    # Fallback if we ever get new values
    return "⚠️"


def format_slot(slot: Optional[Dict[str, Any]]) -> str:
    """
    Turn a morning/afternoon dict into a compact emoji cell like '🧶 ✅'.
    If the slot is None (non-work day), return a dash.
    """
    if not slot:
        return "—"

    outerwear = slot.get("outerwear")
    walk_score = slot.get("walk_score")

    clothes_emoji = emoji_for_outerwear(outerwear)
    walk_emoji = emoji_for_walk_score(walk_score)

    return f"{clothes_emoji} {walk_emoji}"


def print_weekly_table(plan: Dict[str, Any]) -> None:
    """
    Print a small emoji table based on the weekly_json structure:

    {
      "generated_at": "...",
      "days": [
        {
          "date": "YYYY-MM-DD",
          "weekday": "Mon",
          "morning": {...} or null,
          "afternoon": {...} or null
        },
        ...
      ]
    }
    """
    days = plan.get("days", [])

    print()
    print("Weekly commute overview")
    gen = plan.get("generated_at")
    if gen:
        print(f"(generated at {gen})")
    print()
    header_day = "Day"
    header_am = "AM"
    header_pm = "PM"
    print(f"{header_day:<4} {header_am:<10} {header_pm:<10}")
    print("-" * 28)

    for day in days:
        weekday = day.get("weekday", "?")
        morning = format_slot(day.get("morning"))
        afternoon = format_slot(day.get("afternoon"))
        print(f"{weekday:<4} {morning:<10} {afternoon:<10}")

    print()


def main() -> None:
    """
    Read weekly_json from stdin and print an emoji table.
    Usage:
        python -m app.src.cli weekly_json | python -m app.src.weekly_pretty
    """
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            print("[weekly_pretty] No input received on stdin. "
                  "Pipe weekly_json into this command, e.g.:")
            print("  python -m app.src.cli weekly_json | python -m app.src.weekly_pretty")
            sys.exit(1)

        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[weekly_pretty] Failed to parse JSON from stdin: {e}")
        sys.exit(1)

    print_weekly_table(data)


if __name__ == "__main__":
    main()
