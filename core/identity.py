"""core/identity.py — who this assistant is.

ONE PLACE FOR THE NAME
    The name used to be a string literal repeated in the UI defaults, the config
    defaults and the prompt injection, which meant three chances to disagree. It
    lives here now and everything else reads it.

    The product is **Ultron**. The upstream application it is built on is MARK
    LVI by FatihMakes, and that attribution stays in the licence and the docs —
    but the assistant in the window, in the prompt and in the logs is Ultron.

WHY THE OLD NAMES ARE STILL RECOGNISED
    Someone will call it Jarvis out of habit, and the wake-word model, the log
    history and the old config files all say so. Being confused about your own
    name is the least robotic thing an assistant can do, so the aliases are
    answered rather than corrected.

WHAT THIS MODULE IS NOT
    It is not a persona. The persona is written in `core/prompt.txt` under
    [MANNER], because prose about how to speak belongs where the model reads it,
    not in code that cannot use it.
"""

from __future__ import annotations

import re

# The name shown on the HUD, spoken by the interface and injected into the
# prompt as {assistant_name}.
NAME = "Ultron"

# How the assistant addresses the user when a form of address is wanted.
ADDRESS = "sir"

# Names people will actually use. Answered, not corrected.
ALIASES = ("Ultron", "Jarvis", "J.A.R.V.I.S", "Mark")

# The upstream project this derivative is built on. Attribution, not identity.
UPSTREAM = "MARK LVI (FatihMakes/Mark-LVI)"
UPSTREAM_LICENSE = "CC BY-NC 4.0"

_CALL_RE = re.compile(
    r"\b(?:hey|hi|ok|okay|hello)?\s*(ultron|jarvis|j\s*\.?\s*a\s*\.?\s*r\s*\.?\s*v\s*\.?\s*i\s*\.?\s*s)\b",
    re.IGNORECASE,
)


def display_name() -> str:
    return NAME


def is_self_name(text: str) -> bool:
    """True when the phrase is one of the names this assistant answers to."""
    cleaned = re.sub(r"[^a-z]", "", str(text or "").lower())
    return cleaned in {re.sub(r"[^a-z]", "", alias.lower()) for alias in ALIASES}


def is_being_addressed(text: str) -> bool:
    """True when the utterance contains a name for the assistant."""
    return bool(_CALL_RE.search(str(text or "")))


def introduction() -> str:
    return f"{NAME}, at your service."


def as_facts() -> dict:
    return {
        "name": NAME,
        "address": ADDRESS,
        "answers_to": list(ALIASES),
        "upstream": UPSTREAM,
        "license": UPSTREAM_LICENSE,
    }
