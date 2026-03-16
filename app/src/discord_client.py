"""
app.src.discord_client
----------------------
Minimal Discord DM client for the commute-plan project.

Behavior:
- Loads environment variables from, in this order:
    1) /srv/2bananas/projects/commute-plan/.env
    2) /srv/2bananas/projects/commute-plan/secrets/.env
    3) Any existing process env (.bashrc, system, etc.)
- Expects at least:
    DISCORD_BOT_TOKEN
    DISCORD_USER_ID_MARK
- Optionally uses:
    DISCORD_APP_ID
    DISCORD_PUBLIC_KEY
- Provides:
    send_message(content: str) -> bool
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

from .logging_setup import get_logger


# --- Environment loading ------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]  # /srv/2bananas/projects/commute-plan
ROOT_ENV = BASE_DIR / ".env"
SECRETS_ENV = BASE_DIR / "secrets" / ".env"
LOG = get_logger("discord-client")


def _load_env_once() -> None:
    """
    Load environment variables from project .env files if present, then from
    the process environment. We try both:
        - BASE_DIR/.env
        - BASE_DIR/secrets/.env
    in that order, without overriding values that already exist.
    """
    loaded_any = False

    for path in (ROOT_ENV, SECRETS_ENV):
        if path.is_file():
            load_dotenv(path, override=False)
            LOG.debug("env_loaded", env_path=str(path))
            loaded_any = True

    if not loaded_any:
        # Last-chance: generic .env in CWD or elsewhere
        load_dotenv(override=False)
        LOG.debug("env_not_found_using_process_env", root_env=str(ROOT_ENV), secrets_env=str(SECRETS_ENV))


_load_env_once()


def _get_config() -> Optional[Dict[str, Any]]:
    """
    Read the Discord config from environment variables.

    Returns a dict if all required pieces are present, otherwise None.
    """
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    user_id = os.getenv("DISCORD_USER_ID_MARK", "").strip()
    app_id = os.getenv("DISCORD_APP_ID", "").strip()
    public_key = os.getenv("DISCORD_PUBLIC_KEY", "").strip()

    # Debug what we see (without leaking the token itself)
    LOG.info(
        "discord_config_loaded",
        token_present=bool(token),
        user_id_present=bool(user_id),
        app_id_present=bool(app_id),
        public_key_present=bool(public_key),
    )

    if not token or not user_id:
        # Minimal viable config is token + target user id
        return None

    return {
        "token": token,
        "user_id": user_id,
        "app_id": app_id,
        "public_key": public_key,
    }


# --- Core DM helpers ----------------------------------------------------------

API_BASE = "https://discord.com/api/v10"


def _create_dm_channel(token: str, user_id: str) -> Optional[str]:
    """
    Create (or retrieve) a DM channel ID for the given user via the bot token.
    Returns the channel ID on success, or None on failure.
    """
    url = f"{API_BASE}/users/@me/channels"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "2bananas-commute-plan/1.0",
    }
    payload = {"recipient_id": user_id}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        LOG.error("dm_channel_create_error", error=str(e))
        return None

    if resp.status_code != 200:
        LOG.error("dm_channel_create_failed", status=resp.status_code, body=resp.text)
        return None

    data = resp.json()
    channel_id = str(data.get("id", "")).strip()
    if not channel_id:
        LOG.error("dm_channel_missing_id")
        return None

    LOG.debug("dm_channel_ready", channel_id=channel_id)
    return channel_id


def _send_channel_message(token: str, channel_id: str, content: str) -> bool:
    """
    Send a message to a specific channel_id.
    Returns True on success.
    """
    url = f"{API_BASE}/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "2bananas-commute-plan/1.0",
    }
    payload = {"content": content}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        LOG.error("dm_send_error", error=str(e))
        return False

    if resp.status_code not in (200, 201):
        LOG.error("dm_send_failed", status=resp.status_code, body=resp.text)
        return False

    LOG.info("dm_send_ok", channel_id=channel_id)
    return True


# --- Public API ---------------------------------------------------------------

def send_message(content: str) -> bool:
    """
    Send a DM to DISCORD_USER_ID_MARK using the bot token from DISCORD_BOT_TOKEN.

    Returns:
        True if we believe the message was delivered, False otherwise.
    """
    cfg = _get_config()
    if not cfg:
        LOG.warning("discord_config_missing")
        return False

    token = cfg["token"]
    user_id = cfg["user_id"]

    LOG.debug("dm_channel_create_start")
    channel_id = _create_dm_channel(token, user_id)
    if not channel_id:
        LOG.error("dm_channel_create_unavailable")
        return False

    LOG.debug("dm_send_start", channel_id=channel_id)
    return _send_channel_message(token, channel_id, content)


if __name__ == "__main__":
    # Simple manual test: send a short ping if config is present
    ok = send_message("Test message from commute-plan discord_client.")
    LOG.info("manual_test_complete", ok=ok)
