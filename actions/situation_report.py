"""actions/situation_report.py - the model asking what is on the machine now.

This is the spoken half of `core/situation.py`: the same read-only snapshot,
shaped as an answer. It exists because "Minecraft is open" should be a fact the
assistant can check, not something the owner has to volunteer.

It never starts, stops or focuses anything. When the answer is "Chrome and
Minecraft are running", the next step is still the owner's call, or a separate
tool that asks first.
"""

from __future__ import annotations


def situation_report(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    only = str(params.get("app") or "").strip()
    detail = str(params.get("detail") or "short").strip().lower()

    try:
        from core import situation
    except Exception as exc:  # a missing module must not take the session down
        return f"I cannot read the program list: {type(exc).__name__}: {exc}"

    try:
        current = situation.snapshot()
        apps = situation.running_apps(only=only) if only else current.apps
    except Exception as exc:
        return f"I cannot read the program list right now: {type(exc).__name__}: {exc}"

    if only:
        if not apps:
            message = f"{only} is not running, as far as I can see."
        else:
            listed = ", ".join(app.describe() for app in apps[:6])
            message = f"{only} is running: {listed}."
        _log(message, player)
        return message

    if detail == "full":
        lines = []
        if current.foreground is not None:
            lines.append(f"In front: {current.foreground.describe()}.")
        for app in current.apps[:10]:
            lines.append(f"- {app.describe()} ({app.kind})")
        if current.note:
            lines.append(f"Note: {current.note}.")
        message = " ".join(lines) if lines else situation.describe(current)
    else:
        message = situation.describe(current)

    _log(message, player)
    return message


def _log(message: str, player=None) -> None:
    print(f"[Situation] {message}")
    if player:
        try:
            player.write_log(f"ULTRON: {message}")
        except Exception:
            pass


TOOL = {
    "name": "situation_report",
    "description": (
        "Reports what is already open on this machine: the program in front and "
        "the other known programs running, with versions where they can be read "
        "(for example 'Minecraft 1.21.4'). Read-only: it does not start, stop, "
        "focus or change anything. Use it when the owner asks what is running, "
        "what they were doing, whether a game or app is open, or before starting "
        "a program that may already be running. Never guess an app list without "
        "calling it."
    ),
    "brief": (
        "Reads what is open now: front app plus running apps and versions. "
        "Read-only; never starts or stops anything."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app": {
                "type": "STRING",
                "description": (
                    "Optional name to check, such as 'Minecraft' or 'Chrome'. "
                    "Leave empty for a summary of everything worth naming."
                ),
            },
            "detail": {
                "type": "STRING",
                "description": (
                    "short for one sentence, full for the list with kinds. "
                    "Default short."
                ),
                "enum": ["short", "full"],
            },
        },
    },
    "handler": situation_report,
}
