"""
app.src.config_loader
----------------------
Helpers to load environment variables and commute config.

Phase 1:
- Load secrets/.env into process env.
- Load secrets/commute_config.toml into a dict.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
import toml
from .logging_setup import get_logger


BASE_DIR = Path(__file__).resolve().parents[2]
SECRETS_DIR = BASE_DIR / "secrets"
LOG = get_logger("config-loader")


def _first_env(*keys: str) -> str:
    for key in keys:
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return ""


def load_env() -> None:
    """
    Load environment variables from secrets/.env (if present).

    Safe to call multiple times. Values already set in os.environ
    will not be overwritten by python-dotenv's defaults, but we
    rely on the file to provide most values.
    """
    env_path = SECRETS_DIR / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    else:
        # Not fatal for now, but useful to know during setup.
        LOG.warning("env_file_missing", env_path=str(env_path))


def load_commute_config() -> Dict[str, Any]:
    """
    Load commute configuration from secrets/commute_config.toml.

    Returns
    -------
    dict
        Nested dictionary keyed by sections (morning, afternoon, etc.).
    """
    cfg_path = SECRETS_DIR / "commute_config.toml"
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Commute config not found: {cfg_path}")

    load_env()

    text = cfg_path.read_text(encoding="utf-8")
    data = toml.loads(text)

    # Env-normalized defaults for callers that rely on these top-level keys.
    tz = _first_env("TZ", "TIMEZONE") or "America/Chicago"
    if _first_env("TIMEZONE") and not _first_env("TZ"):
        LOG.debug("timezone_fallback_used", from_key="TIMEZONE", to_key="TZ")

    work_days_raw = _first_env("WORK_DAYS")
    work_days = [d.strip() for d in work_days_raw.split(",") if d.strip()]

    data.setdefault("tz", tz)
    data.setdefault("timezone", tz)
    data.setdefault("work_days", work_days)
    data.setdefault("weather_json", _first_env("WEATHER_JSON") or str(BASE_DIR / "data" / "tulsa_weather.json"))
    data.setdefault("state_file", _first_env("STATE_FILE") or "data/last_plan.json")
    return data
