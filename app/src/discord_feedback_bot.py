"""
app.src.discord_feedback_bot
----------------------------
Discord DM listener that lets you log "comfort feedback" any time of day.

It listens for DMs from your configured user ID (DISCORD_USER_ID_MARK) and
accepts commands like:

  !log context=commute leg=morning activity=walked comfort=too_cold wore="light jacket + hat"
  !log context=laps activity=laps comfort=too_hot wore="t-shirt" location="work parking lot"
  !log time="2025-12-12 07:05" context=commute leg=morning activity=walked comfort=ok wore="hoodie"

It stores:
- your fields (context/leg/activity/wore/comfort/location)
- nearest hourly weather snapshot from cached tulsa_weather.json
- raw hourly blob for future analysis

Notes:
- This uses the Gateway (not webhooks). You must enable the bot + DM it.
- If "Message Content Intent" is required by your Discord app settings,
  you may need to enable it in the Developer Portal.
"""

from __future__ import annotations

import argparse
import json
import re
import os
import shlex
# >>> BEGIN: walk_dropdown_imports >>>
import urllib.request
import urllib.error
# <<< END: walk_dropdown_imports <<<

from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import disnake
from dotenv import load_dotenv

from .comfort_db import ComfortLog, get_db_path, insert_comfort_log, wear_level_desc
from .weather_reader import load_weather_json
from .logging_setup import get_logger


# -----------------------------------------------------------------------------
# Env loading (mirror discord_client.py behavior)
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]  # /srv/2bananas/projects/commute-plan
ROOT_ENV = BASE_DIR / ".env"
SECRETS_ENV = BASE_DIR / "secrets" / ".env"
LOG = get_logger("discord-feedback-bot")


def _load_env_once() -> None:
    loaded_any = False
    for p in (ROOT_ENV, SECRETS_ENV):
        if p.is_file():
            load_dotenv(p, override=False)
            LOG.info("env_loaded", env_path=str(p))
            loaded_any = True
    if not loaded_any:
        load_dotenv(override=False)
        LOG.info("env_not_found_using_process_env")


_load_env_once()


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _parse_timestamp_local(raw: str) -> datetime:
    raw = (raw or "").strip().lower()
    if raw in ("", "now", "today"):
        return datetime.now()
    if " " in raw and "t" not in raw:
        raw = raw.replace(" ", "T")
    return datetime.fromisoformat(raw)


def _to_local_time(dt_utc: datetime, tz_offset_seconds: int) -> datetime:
    return (dt_utc + timedelta(seconds=tz_offset_seconds)).replace(tzinfo=None)


def _find_nearest_hourly(data: Dict[str, Any], target_local: datetime) -> Tuple[Optional[Dict[str, Any]], Optional[datetime]]:
    hourly = data.get("hourly") or []
    tz_offset = int(data.get("timezone_offset", 0))
    best = None
    best_local = None
    best_abs = None

    for entry in hourly:
        try:
            ts = int(entry.get("dt"))
        except Exception:
            continue
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        dt_local = _to_local_time(dt_utc, tz_offset)
        delta = abs((dt_local - target_local).total_seconds())
        if best_abs is None or delta < best_abs:
            best_abs = delta
            best = entry
            best_local = dt_local

    return best, best_local


def _pop_to_pct(pop_raw: Any) -> Optional[float]:
    if pop_raw is None:
        return None
    try:
        v = float(pop_raw)
    except Exception:
        return None
    if v <= 1.0:
        return round(v * 100.0, 2)
    return round(v, 2)


def _extract_weather_fields(hourly_entry: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    def f(key: str) -> Optional[float]:
        v = hourly_entry.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

    out["temp_f"] = f("temp")
    out["feels_like_f"] = f("feels_like")
    out["wind_speed_mph"] = f("wind_speed")
    out["wind_gust_mph"] = f("wind_gust")

    h = hourly_entry.get("humidity")
    try:
        out["humidity_pct"] = float(h) if h is not None else None
    except Exception:
        out["humidity_pct"] = None

    out["pop_pct"] = _pop_to_pct(hourly_entry.get("pop"))
    out["raw_weather_json"] = json.dumps(hourly_entry, separators=(",", ":"), ensure_ascii=False)

    return out


# -----------------------------------------------------------------------------
# Command parsing
# -----------------------------------------------------------------------------
HELP_TEXT = (
    "Commute feedback commands:\n"
    "  !log key=value key=value ...\n\n"
    "Keys:\n"
    "  context=commute|laps|errand|...\n"
    "  leg=morning|afternoon|lunch|...\n"
    "  activity=walked|drove|laps|...\n"
    "  comfort=ok|too_cold|too_hot|...\n"
    "  wore=\"free text\"\n"
    "  location=\"free text\"\n"
    "  time=\"YYYY-MM-DD HH:MM\" (or ISO) (default: now)\n\n"
    "Examples:\n"
    "  !log context=commute leg=morning activity=walked comfort=ok wore=\"hoodie\"\n"
    "  !log context=laps activity=laps comfort=too_hot wore=\"t-shirt\" location=\"work\"\n"
)




# >>> BEGIN: normalize_level_keys >>>
def _normalize_level_key(k: str) -> str:
    k = (k or "").strip().lower()
    if k in ("level", "lvl", "wore_level", "wore-level"):
        return "wore_level"
    return k
# <<< END: normalize_level_keys <<<

def _parse_kv(tokens: list[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for t in tokens:
        if "=" not in t:
            continue
        k, v = t.split("=", 1)
        k = k.strip().lower()
        k = _normalize_level_key(k)
        v = v.strip()
        if not k:
            continue
        out[k] = v
    return out


def parse_log_command(content: str) -> Optional[Dict[str, str]]:
    raw = (content or "").strip()
    if not raw:
        return None

    low = raw.lower().strip()
    if low in ("!help", "help", "!?", "?"):
        return {"_cmd": "help"}
    # >>> BEGIN: walk_command_parse >>>
    if low.startswith("!walk") or low.startswith("walk"):
        return {"_cmd": "walk"}
    # <<< END: walk_command_parse <<<


    if low.startswith("!log") or low.startswith("log"):
        # tokenize respecting quotes
        toks = shlex.split(raw)
        # drop leading command token
        toks = toks[1:] if toks else []
        # >>> BEGIN: parse_level_shorthand >>>
        # Allow shorthand tokens like: lvl3, level3, l3
        for t in list(toks):
            if "=" in t:
                continue
            m2 = re.match(r"^(?:lvl|level|l)([1-5])$", t.strip().lower())
            if m2:
                toks.append("wore_level=" + m2.group(1))

        # <<< END: parse_level_shorthand <<<
        data = _parse_kv(toks)
        data["_cmd"] = "log"
        return data

    return None


def build_row_from_fields(fields: Dict[str, str], source: str) -> Tuple[ComfortLog, Optional[str]]:
    # time
    t_raw = fields.get("time", "now")
    target_local = _parse_timestamp_local(t_raw)

    # your fields
    context = (fields.get("context") or "commute").strip() or "commute"
    leg = (fields.get("leg") or "").strip() or None
    activity = (fields.get("activity") or "").strip() or None
    comfort = (fields.get("comfort") or "").strip() or None
    wore = (fields.get("wore") or "").strip() or None
    wore_level = (fields.get("wore_level") or "").strip()
    try:
        wore_level_i = int(wore_level) if wore_level else None
    except Exception:
        wore_level_i = None
    if wore_level_i not in (1,2,3,4,5):
        wore_level_i = None
    location = (fields.get("location") or "").strip() or None

    # weather snapshot
    data = load_weather_json()
    entry, entry_local = _find_nearest_hourly(data, target_local)

    weather_fields: Dict[str, Any] = {}
    nearest_str: Optional[str] = None
    if entry is not None:
        weather_fields = _extract_weather_fields(entry)
        if entry_local is not None:
            nearest_str = entry_local.isoformat(timespec="minutes")

    row = ComfortLog(
        timestamp_local=target_local.isoformat(timespec="seconds"),
        source=source,
        context=context,
        leg=leg,
        location=location,
        wore=wore,
        wore_level=wore_level_i,
        comfort=comfort,
        activity=activity,
        temp_f=weather_fields.get("temp_f"),
        feels_like_f=weather_fields.get("feels_like_f"),
        wind_speed_mph=weather_fields.get("wind_speed_mph"),
        wind_gust_mph=weather_fields.get("wind_gust_mph"),
        humidity_pct=weather_fields.get("humidity_pct"),
        pop_pct=weather_fields.get("pop_pct"),
        raw_weather_json=weather_fields.get("raw_weather_json"),
    )
    return row, nearest_str


def summarize_row(row: ComfortLog, nearest_hour: Optional[str], new_id: Optional[int] = None) -> str:
    parts = []
    if new_id is not None:
        parts.append(f"✅ Logged feedback (id={new_id})")
    else:
        parts.append("🟦 Parsed feedback (dry-run)")

    parts.append(f"• time: {row.timestamp_local}")
    parts.append(f"• context: {row.context}")
    if row.leg: parts.append(f"• leg: {row.leg}")
    if row.activity: parts.append(f"• activity: {row.activity}")
    if row.wore: parts.append(f"• wore: {row.wore}")
    if row.wore_level: parts.append(f"• wore_level: {row.wore_level} ({wear_level_desc(row.wore_level)})")
    if row.comfort: parts.append(f"• comfort: {row.comfort}")
    if row.location: parts.append(f"• location: {row.location}")

    if row.temp_f is None:
        parts.append("• weather: (no hourly match)")
    else:
        when = nearest_hour or "?"
        parts.append(
            f"• weather@{when}: temp={row.temp_f}F feels={row.feels_like_f}F "
            f"wind={row.wind_speed_mph} gust={row.wind_gust_mph} hum={row.humidity_pct}% pop={row.pop_pct}%"
        )

    return "\n".join(parts)


# -----------------------------------------------------------------------------
# Bot
# >>> BEGIN: walk_dropdown_flow >>>
# -----------------------------------------------------------------------------
# Walk quick-log: DM dropdown UI that POSTs to the comfort API
# -----------------------------------------------------------------------------

WALK_NONE = "__none__"  # non-empty sentinel required by Discord component rules


def _safe_value(v) -> str:
    """
    Discord requires option.value length 1..100 and it must be a string.
    """
    v = "" if v is None else str(v)
    v = v.strip()
    if not v:
        v = WALK_NONE
    if len(v) > 100:
        v = v[:100]
    if len(v) < 1:
        v = "x"
    return v


def _opt(label: str, value) -> "disnake.SelectOption":
    vv = _safe_value(value)
    # Defaults are handled by WalkView._apply_ui_state() (option.default)
    return disnake.SelectOption(label=label, value=vv)


def _val_or_none(v) -> str | None:
    vv = _safe_value(v)
    if vv == WALK_NONE:
        return None
    return vv


def _post_json(url: str, payload: dict, timeout: float = 8.0):
    """
    Minimal JSON POST without requests dependency.
    Returns (ok: bool, resp: dict|str)
    """
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            try:
                return True, json.loads(body)
            except Exception:
                return True, body
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = str(e)
        return False, f"HTTPError {getattr(e,'code','?')}: {body}"
    except urllib.error.URLError as e:
        return False, f"URLError: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


class WalkView(disnake.ui.View):
    """
    Stateful View: selections persist and the dropdown placeholder reflects choices.
    Also sets option.default so the chosen value "sticks".
    """

    def __init__(self, *, api_base: str, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.api_base = (api_base or "").rstrip("/")


        # message reference (set by handler after send)
        self.message: disnake.Message | None = None
        self.context: str | None = None
        self.leg: str | None = None
        self.comfort: str | None = None
        self.wore_level: int | None = None

        self._build()
    async def on_timeout(self) -> None:
        # Disable all components when the view times out.
        try:
            for child in list(getattr(self, "children", []) or []):
                if hasattr(child, "disabled"):
                    child.disabled = True
        except Exception:
            pass

        # If we have a message reference, edit it with a friendly hint.
        if self.message is None:
            return
        try:
            hint = "\n\n(⏳ Timed out — send `!walk` to open a new menu.)"
            await self.message.edit(content=self.render() + hint, view=self)
        except Exception:
            pass

    def render(self) -> str:
        def fmt(k: str, v) -> str:
            return f"• {k}: {v if v not in (None, '') else '—'}"

        lines = [
            "🟦 **Log a walk** — choose values, then press **Submit**",
            "",
            fmt("context", self.context),
            fmt("leg", self.leg),
            fmt("comfort", self.comfort),
            fmt("wore_level", self.wore_level),
            "",
            "Tip: use `!log ...` for fully custom free-text logging.",
        ]
        return "\n".join(lines)

    def _apply_ui_state(self) -> None:
        self.sel_context.placeholder = f"Context: {self.context}" if self.context else "Context"
        self.sel_leg.placeholder = f"Leg: {self.leg}" if self.leg else "Leg (time-of-day)"
        self.sel_comfort.placeholder = f"Comfort: {self.comfort}" if self.comfort else "Comfort"
        self.sel_wore.placeholder = f"Wore level: {self.wore_level}" if self.wore_level else "Wore level (1=light → 5=heavy)"

        def set_defaults(select: disnake.ui.StringSelect, selected: str | None):
            sel = _safe_value(selected or WALK_NONE)
            for opt in select.options:
                opt.default = (opt.value == sel)

        set_defaults(self.sel_context, self.context)
        set_defaults(self.sel_leg, self.leg)
        set_defaults(self.sel_comfort, self.comfort)
        set_defaults(self.sel_wore, str(self.wore_level) if self.wore_level else None)

    def _build(self) -> None:
        self.clear_items()

        self.sel_context = disnake.ui.StringSelect(
            custom_id="walk_context",
            placeholder="Context",
            min_values=1,
            max_values=1,
            options=[
                _opt("Commute", "commute"),
                _opt("Laps", "laps"),
                _opt("Errand", "errand"),
                _opt("Other", "other"),
            ],
        )

        self.sel_leg = disnake.ui.StringSelect(
            custom_id="walk_leg",
            placeholder="Leg (time-of-day)",
            min_values=1,
            max_values=1,
            options=[
                _opt("Morning", "morning"),
                _opt("Lunch", "lunch"),
                _opt("Afternoon", "afternoon"),
                _opt("Evening", "evening"),
                _opt("— (none)", WALK_NONE),
            ],
        )

        self.sel_comfort = disnake.ui.StringSelect(
            custom_id="walk_comfort",
            placeholder="Comfort",
            min_values=1,
            max_values=1,
            options=[
                _opt("OK", "ok"),
                _opt("A bit cold", "a_bit_cold"),
                _opt("Too cold", "too_cold"),
                _opt("A bit hot", "a_bit_hot"),
                _opt("Too hot", "too_hot"),
                _opt("— (none)", WALK_NONE),
            ],
        )

        self.sel_wore = disnake.ui.StringSelect(
            custom_id="walk_wore",
            placeholder="Wore level (1=light → 5=heavy)",
            min_values=1,
            max_values=1,
            options=[
                _opt("1 (very light)", "1"),
                _opt("2", "2"),
                _opt("3", "3"),
                _opt("4", "4"),
                _opt("5 (very heavy)", "5"),
                _opt("— (none)", WALK_NONE),
            ],
        )

        async def on_ctx(inter: disnake.MessageInteraction):
            self.context = _val_or_none(self.sel_context.values[0])
            self._apply_ui_state()
            await inter.response.edit_message(content=self.render(), view=self)

        async def on_leg(inter: disnake.MessageInteraction):
            self.leg = _val_or_none(self.sel_leg.values[0])
            self._apply_ui_state()
            await inter.response.edit_message(content=self.render(), view=self)

        async def on_comfort(inter: disnake.MessageInteraction):
            self.comfort = _val_or_none(self.sel_comfort.values[0])
            self._apply_ui_state()
            await inter.response.edit_message(content=self.render(), view=self)

        async def on_wore(inter: disnake.MessageInteraction):
            raw = _val_or_none(self.sel_wore.values[0])
            try:
                n = int(raw) if raw is not None else None
            except Exception:
                n = None
            self.wore_level = n if n in (1, 2, 3, 4, 5) else None
            self._apply_ui_state()
            await inter.response.edit_message(content=self.render(), view=self)

        self.sel_context.callback = on_ctx
        self.sel_leg.callback = on_leg
        self.sel_comfort.callback = on_comfort
        self.sel_wore.callback = on_wore

        btn_submit = disnake.ui.Button(label="Submit", style=disnake.ButtonStyle.success, custom_id="walk_submit")
        btn_cancel = disnake.ui.Button(label="Cancel", style=disnake.ButtonStyle.secondary, custom_id="walk_cancel")

        async def on_submit(inter: disnake.MessageInteraction):
            payload = {
                "timestamp_local": datetime.now().isoformat(timespec="seconds"),
                "source": "discord_walk",
                "context": self.context or "commute",
                "leg": self.leg,
                "activity": "walked",
                "comfort": self.comfort,
                "wore_level": self.wore_level,
            }

            ok, resp = _post_json(f"{self.api_base}/comfort-log", payload)
            if not ok:
                await inter.response.edit_message(content=f"❌ API rejected: {resp}", view=None)
                return

            tid = None
            if isinstance(resp, dict):
                # Common patterns: {"ok": true, "id": 123} or {"id":123}
                if resp.get("id") is not None:
                    tid = resp.get("id")

            ctx = (self.context or "commute")
            leg = (self.leg or "—")
            comfort = (self.comfort or "—")
            lvl = (f"lvl{self.wore_level}" if self.wore_level else "lvl—")
            detail = f"{ctx} / {leg} / {comfort} / {lvl}"

            if tid is not None:
                msg = f"✅ Logged walk (id={tid}) — {detail}"
            else:
                msg = f"✅ Logged walk — {detail}"

            await inter.response.edit_message(content=msg, view=None)

        async def on_cancel(inter: disnake.MessageInteraction):
            await inter.response.edit_message(content="Cancelled.", view=None)

        btn_submit.callback = on_submit
        btn_cancel.callback = on_cancel

        self.add_item(self.sel_context)
        self.add_item(self.sel_leg)
        self.add_item(self.sel_comfort)
        self.add_item(self.sel_wore)
        self.add_item(btn_submit)
        self.add_item(btn_cancel)

        self._apply_ui_state()


# <<< END: walk_dropdown_flow <<<

class FeedbackBot(disnake.Client):
    def __init__(self, allowed_user_id: str, **kwargs: Any):
        super().__init__(**kwargs)
        self.allowed_user_id = allowed_user_id

    async def on_ready(self) -> None:
        LOG.info("bot_ready", user=str(self.user), user_id=str(getattr(self.user, "id", None)))
        LOG.info("dm_listener_ready", allowed_user_id=self.allowed_user_id)

    async def on_message(self, message: disnake.Message) -> None:
        # Ignore self
        if message.author and self.user and message.author.id == self.user.id:
            return

        # Only DMs
        if message.guild is not None:
            return

        author_id = str(getattr(message.author, "id", "")).strip()
        if not author_id or author_id != self.allowed_user_id:
            return

        cmd = parse_log_command(message.content or "")
        if not cmd:
            return

        if cmd.get("_cmd") == "help":
            await message.channel.send(HELP_TEXT)
            LOG.info("help_command_sent", author_id=author_id)
            return


                
        # >>> BEGIN: walk_command_handler >>>
        # Handle '!walk' as an interactive dropdown flow (stateful view)
        if cmd.get("_cmd") == "walk":
            try:
                api_base = _env("COMFORT_API_BASE") or "http://127.0.0.1:8099"
                view = WalkView(api_base=api_base)
                sent = await message.channel.send(view.render(), view=view)
                try:
                    view.message = sent
                except Exception:
                    pass
                LOG.info("walk_menu_opened", author_id=author_id, api_base=api_base)
            except Exception as e:
                LOG.error("walk_menu_open_failed", author_id=author_id, error=str(e))
                await message.channel.send(f"❌ Could not open walk menu: {e}")
            return
        # <<< END: walk_command_handler <<<
        if cmd.get("_cmd") != "log":
            return

        try:
            row, nearest = build_row_from_fields(cmd, source="discord")
        except Exception as e:
            LOG.error("log_command_parse_failed", author_id=author_id, error=str(e))
            await message.channel.send(f"❌ Could not parse/log that. Error: {e}\n\n{HELP_TEXT}")
            return

        # Insert
        try:
            new_id = insert_comfort_log(row, db_path=get_db_path())
        except Exception as e:
            LOG.error("db_insert_failed", author_id=author_id, error=str(e))
            await message.channel.send(f"❌ DB insert failed: {e}")
            return

        LOG.info("feedback_logged", author_id=author_id, row_id=new_id, nearest_hour=nearest)
        await message.channel.send(summarize_row(row, nearest, new_id=new_id))


def run_bot() -> int:
    token = _env("DISCORD_BOT_TOKEN")
    allowed_user_id = _env("DISCORD_USER_ID_MARK")

    if not token:
        LOG.error("missing_discord_bot_token")
        return 1
    if not allowed_user_id:
        LOG.error("missing_discord_user_id_mark")
        return 1

    intents = disnake.Intents.default()
    intents.messages = True
    intents.dm_messages = True
    # Message content may require an explicit intent toggle in the dev portal
    intents.message_content = True

    bot = FeedbackBot(allowed_user_id=allowed_user_id, intents=intents)
    bot.run(token)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Discord DM feedback bot (comfort logging)")
    ap.add_argument("--parse-test", default="", help="Parse a sample command string and print the row (no insert).")
    ap.add_argument("--insert", action="store_true", help="With --parse-test, actually insert into DB.")
    args = ap.parse_args(argv)

    if args.parse_test:
        cmd = parse_log_command(args.parse_test)
        if not cmd:
            print("❌ Not a recognized command. Try:")
            print(HELP_TEXT)
            return 2
        if cmd.get("_cmd") == "help":
            print(HELP_TEXT)
            return 0
        row, nearest = build_row_from_fields(cmd, source="cli_test")
        if args.insert:
            new_id = insert_comfort_log(row, db_path=get_db_path())
            print(summarize_row(row, nearest, new_id=new_id))
        else:
            print(summarize_row(row, nearest, new_id=None))
            print("\n(raw row dict)")
            print(json.dumps(asdict(row), indent=2))
        return 0

    return run_bot()


if __name__ == "__main__":
    raise SystemExit(main())
