"""hypit.py — bridge to Hypit.

This plugin does not reimplement Hypit. It checks that Hypit is really here and
then makes one bounded call to it; when it is absent it says so in a sentence you
can act on. The transport lives in core/bridges.py, one place for all five bridges,
with a timeout, no shell and an output cap.

Actions: help, and command (one Hypit subcommand plus its target).
"""

from core import bridges

PLUGIN = {
    "name": "hypit_bridge",
    "description": (
        "Runs the Hypit video-cloning CLI: take a reference video and produce variants. Use it when the user wants to clone a video's format and Node.js is installed."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {"type": "STRING",
                        "description": "For action=command: the subcommand"},
            "target": {"type": "STRING",
                       "description": "The video or project to give it"},
        },
        "required": ["action"],
    },
    "tier": "GUARDED",
}


def run(parameters, player=None, session_memory=None):
    bridge = bridges.get("hypit")
    if bridge is None:
        return "Hypit is not wired in this build."
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
