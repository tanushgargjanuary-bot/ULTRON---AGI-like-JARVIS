"""rea_bridge.py — bridge to REA.

This plugin does not reimplement REA. It checks that REA is really here and
then makes one bounded call to it; when it is absent it says so in a sentence you
can act on. The transport lives in core/bridges.py, one place for all five bridges,
with a timeout, no shell and an output cap.

Two actions: help (asks the installed REA for its own command list) and
command (runs one subcommand, with its arguments passed as a list — never
as a shell string).
"""

from core import bridges

PLUGIN = {
    "name": "rea_bridge",
    "description": (
        "Runs a REA reverse-engineering command: capture a desktop application, inspect a captured app's state, or call any REA subcommand. Use it when the user wants to reverse engineer an application or binary and REA is installed."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": (
                           "Which call to make: 'help' asks REA for its own command list, 'command' runs one subcommand."),
                       "enum": ["help", "command"]},
            "command": {"type": "STRING",
                        "description": "For action=command: the REA subcommand"},
            "args": {"type": "ARRAY", "items": {"type": "STRING"},
                     "description": "Arguments for the subcommand"},
        },
        "required": ["action"],
    },
    "tier": "GUARDED",
}


def run(parameters, player=None, session_memory=None):
    bridge = bridges.get("rea")
    if bridge is None:
        return "REA is not wired in this build."
    ready, detail = bridge.probe()
    if not ready:
        return detail
    action = str(parameters.get("action") or "").strip().lower()
    if action not in bridge.operations:
        # The caller does not know this tool's vocabulary. Pick the one operation
        # that is always safe: ask it to describe itself.
        action = "status" if "status" in bridge.operations else "help"
    kwargs = {key: value for key, value in parameters.items()
              if key not in ("action", "target", "method", "payload") or value}
    kwargs.pop("action", None)
    return bridge.run(action, **kwargs)
