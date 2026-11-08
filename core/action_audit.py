"""One after-action line: what risk tier applied, and what the tool reported.

This is observability only. It does not authorize, block, retry, or verify an action.
`core.policy` remains the authority, and the returned outcome is copied from the tool
result rather than guessed from the action name.
"""

from __future__ import annotations

from core import policy


def after_action(tool: str, args: dict, result: str) -> str:
    """A short HUD line for a non-observe action; empty for read-only tools.

    No arguments or result body are copied into the HUD line. This avoids exposing
    message contents, file paths, or other values in a general activity log.
    """
    decision = policy.decide(tool, args)
    if decision.tier == policy.Tier.OBSERVE:
        return ""
    text = str(result or "")
    status = "unlabelled"
    if text.startswith("status="):
        status = text.split(None, 1)[0].partition("=")[2][:24] or status
    return f"AFTER: tool={str(tool)[:48]} risk={decision.tier.value} outcome={status}"
