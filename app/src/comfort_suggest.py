"""
app.src.comfort_suggest
-----------------------
Analyze comfort_logs in data/comfort.db and print simple threshold suggestions.

This is intentionally lightweight and conservative:
- It prints stats + "candidate" thresholds only when you have enough data.
- It leverages wore_level (1..5) as your wearable system.

Run:
  python -m app.src.comfort_suggest
  python -m app.src.comfort_suggest --min-samples 5 --comfy-target 0.70
"""

from __future__ import annotations

import argparse
import math
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .comfort_db import get_db_path


# -----------------------------------------------------------------------------
# Data model / normalization
# -----------------------------------------------------------------------------

COMFY_SET = {"comfortable", "ok"}
COLD_SET = {"too_cold", "a_bit_cold"}
HOT_SET = {"too_hot", "a_bit_hot"}


def _norm(s: Any) -> str:
    return (str(s or "")).strip().lower()


def _is_comfy(raw: str) -> bool:
    c = _norm(raw)
    # Treat 'a_bit_*' as 'comfy enough' for tuning. We'll refine later if needed.
    return c in (
        "comfortable",
        "ok",
        "a_bit_cold",
        "a_bit_hot",
        "a bit cold",
        "a bit hot",
    )
