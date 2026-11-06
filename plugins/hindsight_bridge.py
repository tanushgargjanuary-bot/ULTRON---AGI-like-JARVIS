"""hindsight_memory.py — bridge to Hindsight.

This plugin does not reimplement Hindsight. It checks that Hindsight is really here and
then makes one bounded call to it; when it is absent it says so in a sentence you
can act on. The transport lives in core/bridges.py, one place for all five bridges,
with a timeout, no shell and an output cap.

The endpoint path is configuration, not a guess: Ultron performs the
request and the user names the documented path. A made-up path that
returns 404 is worse than being told to set one.
"""

from core import bridges

PLUGIN = {
    "name": "hindsight_bridge",
    "description": (
        "Talks to a running Hindsight memory service: check it is up, or call one of its documented endpoints to retain or recall memory. Use it when the user has Hindsight running and wants its long-term memory, not Ultron's own memory store."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": (
                           "Which call to make: 'status' reads /health, 'request' calls one endpoint."),
                       "enum": ["status", "request"]},
            "path": {"type": "STRING",
                     "description": "Endpoint path starting with /, for example /health"},
            "method": {"type": "STRING", "description": "GET or POST"},
            "payload": {"type": "OBJECT", "description": "JSON body for POST"},
        },
        "required": ["action"],
    },
    "tier": "GUARDED",
}


def run(parameters, player=None, session_memory=None):
    bridge = bridges.get("hindsight")
    if bridge is None:
        return "Hindsight is not wired in this build."
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
