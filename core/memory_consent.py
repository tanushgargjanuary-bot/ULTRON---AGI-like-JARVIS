"""core/memory_consent.py — remembering is a decision the user makes, not a side effect.

The rule is one line: *only what the user approves is remembered.* It was not
true. `core/policy.py` has always classified `save_memory` as GUARDED — "memory
is permanent — remembering is approval-gated" — but the inline tool path in
`main.py` never asked the policy anything, so the verdict existed and the write
happened anyway. A rule enforced nowhere is a comment.

This module is the whole enforcement: one function, called where the write used
to be.

WHY THERE IS NO "DID THE USER ALREADY ASK?" SHORTCUT
    It is tempting to skip the prompt when the utterance contained "remember".
    It is also how "do you remember what I told you?" gets saved silently: the
    classifier would have to be right about intent, and being wrong in that
    direction writes something permanent without asking. Asking every time is
    one extra confirmation for a *permanent* change — not the trivial-action
    prompting the user objects to.

WHAT IT RETURNS
    The dict that goes back to the model as the tool result. Two shapes:
      {"result": "ok", "silent": True}      written — the caller may stay quiet
      {"result": "[CONFIRMATION_PENDING] …"} nothing written yet; the model is
                                            told to ask, and must not claim it done
      {"result": "Nothing was saved: …"}    malformed, so no banner is wasted

    The pending sentence comes from `core/confirm.py`, which already speaks to
    the model in exactly that way for shutdown and settings changes.
"""

from __future__ import annotations

from typing import Callable

from core import confirm, policy

PENDING_MARKER = "[CONFIRMATION_PENDING]"
EMPTY_ANSWER = "Nothing was saved: I need both a key and a value."


def _sentence(category: str, key: str, value: str) -> str:
    """What the confirmation banner says. Short, and it shows the value verbatim
    so the user is approving the fact, not a summary of it."""
    shown = value if len(value) <= 160 else value[:157] + "…"
    return f"Remember “{key}” in {category}: {shown}"


def request_write(
    category: str,
    key: str,
    value: str,
    write: Callable[[dict], object],
    gate: Callable[..., str] | None = None,
    decide: Callable[..., object] | None = None,
) -> dict:
    """Ask, then write. Returns the tool result dict — the only thing the caller
    needs to know is in there.

    `write`, `gate` and `decide` are injectable so the rule can be tested without
    a HUD, a policy table or a disk write. They default to the real ones.
    """
    category = str(category or "notes").strip() or "notes"
    key = str(key or "").strip()
    value = str(value or "").strip()
    if not (key and value):
        return {"result": EMPTY_ANSWER}

    verdict = (decide or policy.decide)("save_memory",
                                        {"category": category, "key": key,
                                         "value": value})
    if getattr(verdict, "allow", False):
        # Nothing in this build allows it. If a future policy ever opens memory
        # writes, it opens them here and nowhere else — the path stays single.
        write({category: {key: {"value": value}}})
        return {"result": "ok", "silent": True}

    if gate is None and confirm.pending_title():
        # The gate holds one pending decision. A second request would replace the
        # first and the fact behind it would vanish with no error anywhere —
        # exactly the silent loss this module exists to prevent.
        return {"result": ("I already have a confirmation on screen. Answer that "
                           "one first, then ask me to remember this.")}

    def run() -> str:
        write({category: {key: {"value": value}}})
        return f"Remembered “{key}” in {category}."

    message = (gate or confirm.request)(
        key=f"memory:{category}:{key}",
        title="Remember this?",
        detail=_sentence(category, key, value),
        run=run,
    )
    # A refused or unanswered gate must not read as a save. `confirm.request`
    # already returns a sentence saying nothing was done when it cannot ask.
    return {"result": str(message)}
