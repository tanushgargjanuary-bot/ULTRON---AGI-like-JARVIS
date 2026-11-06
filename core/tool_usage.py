"""Which tools are actually called — the other half of a trigger.

A condition in the instruction is a hope. The owner asked the right question about it:

    "they need a condition to get triggered, otherwise ULTRON will never use them"

A tool can be declared, described, permitted and still never be chosen. Nothing in
this project could tell the difference between "the user never needed it" and "the
model never once thought of it", because nothing counted the calls.

This module counts them. One line in the call path, one small object in the settings
file, and afterwards the question has an answer:

    usage.unused(all_tool_names)   -> the tools that have never been called
    usage.render(all_tool_names)   -> that answer in words, for tools_status

WHAT IT DELIBERATELY IS NOT
    Not analytics, not a profile, and not networked. It holds a count and a date per
    tool name, on this machine, in the settings file the owner can open and delete.
    Nothing here records what was asked, only which hand was used.
"""

from __future__ import annotations

import time

from core import failures
from memory import config_manager as settings

KEY = "tool_usage"
MAX_TOOLS = 200            # far more than the tool count; a bound, not a target


def _iso(now: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(now))


def note(name: str) -> None:
    """Record one call of one tool. Never raises: a statistic is not worth a turn.

    A tool that fails after this point still counts as used, because the question
    being answered is "did the model reach for it", not "did it succeed". Failures
    have their own trail (`core/failures.py`).
    """
    try:
        name = str(name or "").strip()
        if not name:
            return
        counts = read()
        row = counts.get(name) if isinstance(counts.get(name), dict) else {}
        counts[name] = {"count": int(row.get("count", 0)) + 1,
                        "last": _iso(time.time())}
        if len(counts) > MAX_TOOLS:
            keep = sorted(counts.items(), key=lambda item: item[1].get("last", ""),
                          reverse=True)[:MAX_TOOLS]
            counts = dict(keep)
        settings.save_tool_usage(counts)
    except Exception as error:                                  # noqa: BLE001
        failures.note("tool_usage.note", error)


def read() -> dict:
    """Every tool that has been called, with its count and the last time."""
    try:
        value = settings.get_tool_usage()
    except Exception as error:                                  # noqa: BLE001
        failures.note("tool_usage.read", error)
        return {}
    return value if isinstance(value, dict) else {}


def unused(names) -> list[str]:
    """The tools that have never been called since this was first recorded."""
    used = read()
    return sorted(str(name) for name in names if str(name) not in used)


def render(names) -> str:
    """One short answer about what has and has not been reached for.

    Said in words rather than a table because it is read out loud, and because the
    useful sentence is the last one: these tools exist and nothing has called them.
    """
    names = [str(name) for name in names]
    if not names:
        return "I have no tools to report on."
    used = read()
    called = [name for name in names if name in used]
    never = unused(names)
    if not used:
        return (f"No tool has been called yet in this install, out of {len(names)}. "
                f"That is what a fresh install looks like — or the sign of a trigger "
                f"that never fires.")
    lines = [f"{len(called)} of {len(names)} tools have been called."]
    busiest = sorted(((name, row.get("count", 0), row.get("last", ""))
                      for name, row in used.items() if name in names),
                     key=lambda row: -row[1])[:5]
    if busiest:
        lines.append("Most used: " + ", ".join(f"{name} ({count})"
                                               for name, count, _last in busiest) + ".")
    if never:
        lines.append(f"Never called ({len(never)}): " + ", ".join(never[:15])
                     + (" …" if len(never) > 15 else "")
                     + ". A tool in this list has a description the model has not "
                       "found a reason to use.")
    else:
        lines.append("Every tool has been called at least once.")
    return " ".join(lines)
