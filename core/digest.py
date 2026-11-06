"""core/digest.py — the daily digest: it tells you, and it does nothing else.

The standing rule for this feature is one sentence: **the digest activates
nothing.** So the module is shaped to make that true by construction, not by
restraint:

    build()     reads three things and returns a plain dict. It opens no socket,
                starts no process, calls no tool, and writes no file.
    render_*()  turns that dict into words. Pure string work.
    should_run() decides whether today's digest is due. No side effects.
    save_last_run() is the SINGLE write in this module, and it writes one date.

Everything that could reach the outside world — news checks, reminders firing,
tool calls — lives in other modules. A digest that quietly did them would be the
worst kind of feature: one the user believes is inert.

WHAT IT REPORTS, AND WHY ONLY THIS
    Facts remembered today, and how many older ones exist. Watched topics. How
    many reminders are set (names, not bodies — the digest has no reason to put
    a message on screen that the user did not ask to see). All of it comes from
    files that already exist on this machine.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

DEFAULT_HOUR = "20:00"
# Categories that hold machine state, not things the user asked me to remember.
SYSTEM_CATEGORIES = frozenset({"monitors"})
STATE_NAME = "digest_state.json"
SPEECH_LIMIT = 240


# ── where things live (no directory is ever created here) ────────────────────
def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def state_path() -> Path:
    return _base_dir() / "memory" / STATE_NAME


def reminder_dir() -> Path:
    """The folder `actions/reminder.py` schedules into.

    The path is written out instead of importing that module, because its own
    helper creates the folder — and a digest that creates a folder is a digest
    that changed the machine.
    """
    return Path.home() / ".jarvis" / "reminders"


# ── reading ──────────────────────────────────────────────────────────────────
def _load_memory() -> dict:
    from memory.memory_manager import load_memory

    data = load_memory()
    return data if isinstance(data, dict) else {}


def _entry(entry) -> tuple[str, str]:
    """(value, date). Entries are {'value','updated'} or a bare string."""
    if isinstance(entry, dict):
        return str(entry.get("value", "")), str(entry.get("updated", ""))
    return str(entry), ""


def _reminders(folder: Path | None = None) -> list[str]:
    folder = folder or reminder_dir()
    try:
        if not folder.is_dir():
            return []
        return sorted(p.stem for p in folder.glob("*.py"))
    except OSError:
        return []


def build(now: datetime | None = None,
          memory: dict | None = None,
          reminders_dir: Path | None = None) -> dict:
    """A read-only snapshot. `memory` and `reminders_dir` are injectable so the
    report can be tested on a fixed store instead of the user's real one."""
    now = now or datetime.now()
    memory = _load_memory() if memory is None else memory
    today_stamp = now.strftime("%Y-%m-%d")

    remembered_today: list[dict] = []
    older = 0
    for category, group in memory.items():
        if category in SYSTEM_CATEGORIES or not isinstance(group, dict):
            continue
        for key, entry in group.items():
            value, stamp = _entry(entry)
            if stamp == today_stamp:
                remembered_today.append({"category": category, "key": str(key),
                                         "value": value})
            else:
                older += 1

    watched = sorted(memory.get("monitors") or {}) if isinstance(
        memory.get("monitors"), dict) else []

    return {
        "date": today_stamp,
        "remembered_today": remembered_today,
        "remembered_older": older,
        "watching": watched,
        "reminders": _reminders(reminders_dir),
    }


# ── writing it out ───────────────────────────────────────────────────────────
def _short(text: str, limit: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_text(digest: dict) -> str:
    """The full digest, for the HUD log and for the model to read out."""
    day = _short(digest.get("date", ""), 10)
    lines = [f"DAILY DIGEST — {day}"]

    today = digest.get("remembered_today") or []
    older = int(digest.get("remembered_older") or 0)
    if today:
        lines.append(f"Remembered today ({len(today)}):")
        for fact in today[:12]:
            lines.append(f"  · {fact['category']}/{fact['key']}: "
                         f"{_short(fact['value'])}")
        if len(today) > 12:
            lines.append(f"  · and {len(today) - 12} more")
    else:
        lines.append("Remembered today: nothing new.")
    if older:
        lines.append(f"Older facts on file: {older}.")

    watching = digest.get("watching") or []
    lines.append("Watching: " + (", ".join(_short(t, 40) for t in watching[:8])
                                if watching else "nothing."))

    reminders = digest.get("reminders") or []
    if reminders:
        lines.append(f"Reminders set ({len(reminders)}): "
                     + ", ".join(_short(r, 30) for r in reminders[:8]))
    else:
        lines.append("Reminders set: none.")

    lines.append("Nothing was started, sent or changed by this report.")
    return "\n".join(lines)


def render_speech(digest: dict) -> str:
    """One short spoken sentence — the digest must not hold the floor."""
    today = len(digest.get("remembered_today") or [])
    reminders = len(digest.get("reminders") or [])
    watching = len(digest.get("watching") or [])

    if not (today or reminders or watching):
        spoken = "Nothing new today. I have not started or changed anything."
    else:
        parts = [f"I remembered {today} new {'thing' if today == 1 else 'things'} today"
                 if today else "Nothing new was remembered today"]
        if reminders:
            parts.append(f"{reminders} {'reminder is' if reminders == 1 else 'reminders are'} set")
        if watching:
            parts.append(f"I am watching {watching} {'topic' if watching == 1 else 'topics'}")
        spoken = ". ".join(parts) + ". Nothing was started or changed."
    return spoken[:SPEECH_LIMIT]


# ── scheduling ───────────────────────────────────────────────────────────────
def _hour_of(text: str) -> tuple[int, int]:
    try:
        hour, _, minute = str(text or DEFAULT_HOUR).partition(":")
        return max(0, min(23, int(hour))), max(0, min(59, int(minute or 0)))
    except (TypeError, ValueError):
        hour, _, minute = DEFAULT_HOUR.partition(":")
        return int(hour), int(minute)


def should_run(now: datetime, hour: str = DEFAULT_HOUR,
               last_run: str = "") -> bool:
    """True when today's digest is due: past the hour, and not done today.

    Two questions, both cheap and both answered from arguments — this function
    reads nothing, so a scheduler can call it as often as it likes.
    """
    wanted_h, wanted_m = _hour_of(hour)
    if (now.hour, now.minute) < (wanted_h, wanted_m):
        return False
    return str(last_run or "") != now.strftime("%Y-%m-%d")


def load_last_run(path: Path | None = None) -> str:
    path = path or state_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("last_run", "")) if isinstance(data, dict) else ""
    except (OSError, ValueError):
        return ""


def save_last_run(day: str, path: Path | None = None) -> bool:
    """The only write in this module: one date, so the digest runs once a day."""
    path = path or state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"last_run": str(day)}, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False
