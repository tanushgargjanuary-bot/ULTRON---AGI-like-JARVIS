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

CHANGED 2026-11-21 — nothing but a read runs while the owner is being asked something
    A confirmation banner is a button, and a button is pressed by a click, or by a key press, or by a
    typed space once it has the focus. `computer_control` sends all three and is a routine tool: it
    runs with no banner of its own. So a model that wanted a banner answered could send the answer
    itself, two calls long, and every promise that "only a person can press it" rested on the model
    not trying. While a confirmation is waiting, a call that is allowed to run is now allowed only if
    it is read-only; any other call is refused with a sentence, and runs when it is asked again after
    the owner has answered. Not covered: a call sent in the same message as the call that raised the
    banner (it is dispatched before the banner exists), and anything that does not come through
    `dispatch` below.
"""

from __future__ import annotations

import asyncio
import json

from core import confirm, display_text, policy
from core import undo as undo_mod

# Only explicitly named observational tools bypass a confirmation. Kept for the
# callers that still import it; `policy` is the authority now.
READ_ONLY = policy.OBSERVE_TOOLS


async def dispatch(fc, handler, player, response_factory):
    name = fc.name
    decision = policy.decide(name, getattr(fc, "args", None))

    if decision.allow:
        waiting = confirm.pending_title()
        if waiting and decision.tier is not policy.Tier.OBSERVE:
            return response_factory(
                id=fc.id,
                name=name,
                response={
                    "result": (
                        f"A confirmation is waiting for the user on the screen: "
                        f"'{display_text.one_line(waiting, 80)}'. I did not run {name}, "
                        f"because it could change the machine or answer that confirmation. "
                        f"Ask the user to answer it first, then try again."
                    )
                },
            )
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
