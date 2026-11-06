"""Human-only, fail-closed action gate for both MARK voice engines.

No Qt imports. The existing confirmation UI schedules work off its GUI thread.
This gates top-level tools, not arbitrary filesystem or plugin Python internals.

CHANGED 2026-11-05 — risk tiers instead of a four-name allowlist
    The gate used to allow exactly four observational tools and put everything
    else behind the HUD banner, so opening a browser cost the same confirmation
    as powering the machine down. Asking that often destroys the value of the
    prompt: the user starts pressing CONFIRM without reading it.

    `core/policy.py` now classifies every call into observe / routine / guarded /
    sensor. Routine calls — the reversible ones the user just asked for — run
    straight through. Guarded and sensor calls keep the original path: frozen
    arguments, a real HUD confirmation, a token only the interface can issue.

    Unknown tools are still guarded. Adding a tool does not add trust.
"""

from __future__ import annotations

import asyncio
import json

from core import confirm, policy
from core import undo as undo_mod

# Only explicitly named observational tools bypass a confirmation. Kept for the
# callers that still import it; `policy` is the authority now.
READ_ONLY = policy.OBSERVE_TOOLS


async def dispatch(fc, handler, player, response_factory):
    name = fc.name
    decision = policy.decide(name, getattr(fc, "args", None))

    if decision.allow:
        # Routine work runs now: the user asked for it and can take it back.
        # Nothing is parked, nothing is frozen, and the undo stack carries it.
        return await handler(fc)

    if confirm.pending_title():
        return response_factory(
            id=fc.id,
            name=name,
            response={
                "result": "Another confirmation is pending. No action was executed."
            },
        )
    loop = asyncio.get_running_loop()
    # Copy the request now: a later mutation of the original model object must
    # not change what the user approved. A simple namespace fits both engines.
    from types import SimpleNamespace

    frozen = SimpleNamespace(
        id=fc.id, name=name, args=json.loads(json.dumps(dict(fc.args or {})))
    )
    detail = json.dumps(frozen.args, ensure_ascii=False, indent=2)
    if len(detail.encode("utf-8")) > 65536:
        return response_factory(
            id=fc.id,
            name=name,
            response={"result": "Arguments exceed approval limit. Nothing executed."},
        )

    def run_approved():
        future = asyncio.run_coroutine_threadsafe(handler(frozen), loop)
        try:
            result = future.result(timeout=300)
        except TimeoutError:
            future.cancel()
            return "Approved tool timed out; execution may have partially completed. Inspect current state."
        payload = getattr(result, "response", result)
        if player is not None:
            player.show_content("Approved action result", str(payload))
        return str(payload)

    message = confirm.request(
        "custom-" + str(fc.id),
        "Approve action: " + name,
        f"Risk: {decision.tier.value} — {decision.reason}\n\nExact tool arguments:\n{detail}",
        run_approved,
    )
    return response_factory(id=fc.id, name=name, response={"result": message})


def verdict(name: str, args=None) -> str:
    """One-line policy answer, for status output and tests."""
    return str(policy.decide(name, args))


def undo_available() -> bool:
    """True when a routine action has something the user can take back."""
    return undo_mod.can_undo()
