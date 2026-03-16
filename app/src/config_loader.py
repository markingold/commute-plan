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

    text = cfg_path.read_text(encoding="utf-8")
    data = toml.loads(text)
    return data
