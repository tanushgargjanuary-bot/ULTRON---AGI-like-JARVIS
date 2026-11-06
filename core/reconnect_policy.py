"""core/reconnect_policy.py — why the session dropped, and what to do about it.

WHY THIS IS A MODULE AND NOT SIX LINES IN main.py
    Because the old six lines were wrong in a way nobody could see. The run loop
    decided "the resumption handle was rejected" by testing whether the string
    "handle" appeared anywhere in the exception text. A dropped socket, a TaskGroup
    teardown, a "cannot schedule new futures after shutdown" — anything that
    happened to contain that word — took the branch meant for an expired handle,
    which set the backoff to ZERO and reconnected immediately. The result is a hot
    loop: connect, die, "SYS: Could not restore the conversation — starting fresh.",
    connect, die. The activity log filled with identical lines and the real error
    never reached the screen.

    A policy that can be read, called and tested is the fix. This file has no
    asyncio, no Qt and no network in it: it takes an exception and a little state
    and returns a decision.

THE RULES
    1. Only a genuine resumption failure drops the handle, and only when there
       was a handle to drop. Matching is on specific markers, not a substring.
    2. Dropping the handle happens at most once per streak. After that the same
       error is an ordinary failure and gets ordinary backoff, so the loop cannot
       spin.
    3. Delay grows: 3, 6, 12, 24, capped at 30 seconds.
    4. The user is told once per streak, in one line, with the error text
       truncated and anything credential-shaped redacted. Later failures in the
       same streak stay off the screen — the log is not a place to shout.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# What counts as "this is about the session, not about the model or the request".
#
# The first version of this list contained the bare status codes "invalid_argument"
# and "not_found", and that reintroduced the very failure it was written to fix,
# one level up: `INVALID_ARGUMENT` is also what the server says when it dislikes
# a tuning field, and `NOT_FOUND` is what it says when a model name is wrong. Both
# were therefore classified as a dead resumption handle, which dropped the handle
# AND skipped the branch that repairs the real cause — so a bad model name turned
# into "Could not restore the conversation" every half second, forever.
#
# A session word AND a failure word, or the word "resum" on its own.
_SESSION_WORDS = ("resum", "handle", "session")
_FAILURE_WORDS = ("invalid", "expired", "not found", "not_found", "unknown",
                  "no longer", "rejected", "closed")

_CREDENTIAL = re.compile(r"(AIza[\w\-]{10,}|sk-[\w\-]{10,}|[A-Za-z0-9_\-]{32,})")

BASE_DELAY = 3.0
MAX_DELAY = 30.0

FIRST_RETRY = 0.5      # after a genuine handle drop: reconnect at once, but not spinning
TELL_USER_AFTER = 3    # failures in one streak before the message changes


@dataclass(frozen=True)
class Verdict:
    """What the run loop should do next. Every field is meant to be used."""

    reason: str                 # short label, for the console
    message: str                # one line for the activity log ("" = say nothing)
    retry_delay: float          # seconds to wait before the next attempt
    drop_handle: bool           # discard the resumption handle before reconnecting
    tell_user: bool             # whether `message` goes on screen

    @property
    def is_storm(self) -> bool:
        return self.reason == "repeated"


def describe(exc: BaseException, limit: int = 160) -> str:
    """One line, no traceback, no credentials, no newlines.

    Error text is the one place a key can leak into a log: providers echo request
    context back. Redaction is by shape (long unbroken token) rather than by name,
    because there is no field name here to match on.
    """
    text = f"{type(exc).__name__}: {exc}"
    text = " ".join(text.split())                     # collapse newlines and runs
    text = _CREDENTIAL.sub("[redacted]", text)
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def looks_like_resumption_failure(exc: BaseException) -> bool:
    """True only for errors that are actually about a resumption handle.

    Two words, not one: a session word and a failure word. "resum" alone is
    enough because no provider says it about anything else.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    if "resum" in text:
        return True
    return (any(w in text for w in _SESSION_WORDS)
            and any(w in text for w in _FAILURE_WORDS))


def classify(exc: BaseException, *, resumed_with: bool, consecutive: int = 0,
             backoff: float = 0.0) -> Verdict:
    """Decide what a dropped session means.

    `resumed_with` says whether this attempt carried a resumption handle;
    `consecutive` is how many attempts have failed in a row before this one, so
    the first failure of a streak is 0.
    """
    try:
        consecutive = max(0, int(consecutive))
    except (TypeError, ValueError):
        consecutive = 0
    detail = describe(exc)

    if resumed_with and consecutive == 0 and looks_like_resumption_failure(exc):
        return Verdict(
            reason="handle-dropped",
            message="SYS: Could not restore the conversation — starting fresh.",
            retry_delay=FIRST_RETRY,
            drop_handle=True,
            tell_user=True,
        )

    delay = min(MAX_DELAY, max(BASE_DELAY, backoff * 2 if backoff else BASE_DELAY))
    # The first two failures of a streak are worth saying out loud: they are how a
    # user learns that a key expired or a model name is wrong. After that the log
    # stops repeating itself and only the delay keeps growing.
    tell = consecutive < 2
    if consecutive == TELL_USER_AFTER:
        # Said once, at the point the streak stops being an incident and starts
        # being a pattern. Said on every attempt after it, this line was itself
        # the wall of identical messages the owner complained about.
        message = f"SYS: Reconnecting — {consecutive + 1} attempts failed. Last: {detail}"
        reason = "repeated"
    elif tell:
        message = f"SYS: Connection dropped — {detail}. Retrying in {delay:.0f}s."
        reason = "backoff"
    elif consecutive > TELL_USER_AFTER:
        message = ""
        reason = "repeated"
    else:
        message = ""
        reason = "backoff"

    return Verdict(
        reason=reason,
        message=message,
        retry_delay=delay,
        drop_handle=False,
        tell_user=tell or bool(message),
    )
