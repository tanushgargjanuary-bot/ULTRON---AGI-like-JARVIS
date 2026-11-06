"""voicestudio.py — bridge to VoiceStudio.

This plugin does not reimplement VoiceStudio. It checks that VoiceStudio is really here and
then makes one bounded call to it; when it is absent it says so in a sentence you
can act on. The transport lives in core/bridges.py, one place for all five bridges,
with a timeout, no shell and an output cap.

Ultron's own speech already works without this. Reach for VoiceStudio
when the user wants one of ITS voices or its cloning, not a replacement
for the configured engine.
"""

from core import bridges

PLUGIN = {
    "name": "voicestudio_bridge",
    "description": (
        "Talks to a running VoiceStudio voice server: check it is up, or call one of its documented endpoints for synthesis, cloning or transcription. Use it when the user runs VoiceStudio locally."
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
    bridge = bridges.get("voicestudio")
    if bridge is None:
        return "VoiceStudio is not wired in this build."
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
