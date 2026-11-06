"""core/close_codes.py — reading a provider's close message without guessing.

A Live session that drops sends one string: a code and a reason. The code alone almost
never says what to do. 1007 is the Live API's generic close and covers a bad key, a bad
model name and a malformed tool list alike — the three need three different answers, and
one of them is "stop and ask the user for a key" while another is "nothing to do with
the key at all".

That distinction was the fault this module fixes. The old test read

    if "API key not valid" in err_str or "1007" in err_str:

so any 1007 opened the re-key panel. A plugin with `required: ["action"]` and no `action`
property made every connect fail with 1007, and the assistant spent the evening asking
for a key that was already right. The user saw "API key invalid" and "Initialised"
alternating, which reads exactly like a bad key.

The rule now: the message decides, not the number. A code is only ever a tie-breaker.
"""

from __future__ import annotations

import re

# The message shapes the provider uses, in the order they must be tested. A schema
# complaint can carry the word "key" inside a path, so it is tested before the key.
SCHEMA = re.compile(r"function_declarations\[\s*(\d+)\s*\]|"
                    r"\bparameters\b.*\bnot defined\b|"
                    r"invalid_argument.*tool|tool.*invalid_argument", re.I)
KEY = re.compile(r"api key not valid|api_key_invalid|invalid api key|"
                 r"incorrect api key|key is invalid", re.I)
QUOTA = re.compile(r"quota|resource_exhausted|rate limit|429", re.I)
MODEL = re.compile(r"model not found|not_found.*model|unsupported model|"
                   r"model .* does not exist", re.I)
NETWORK = re.compile(r"timeout|timed out|getaddrinfo|cancellederror|"
                     r"connectionrefused|cannot connect|network", re.I)


def rejected_declaration(message: str) -> int | None:
    """The index of the tool declaration the server refused, or None.

    None means "the message does not say one was refused" — not "none was refused".
    A caller that treats None as "all fine" without reading `kind` would repeat the
    mistake this module exists for.
    """
    found = re.search(r"function_declarations\[\s*(\d+)\s*\]", str(message))
    if found:
        return int(found.group(1))
    if SCHEMA.search(str(message)):
        return 0            # named no index, but said the schema was wrong
    return None


def kind(message: str, code: int | None = None) -> str:
    """What this close message is about: schema, key, quota, model, network or other.

    `code` is accepted and used only when the text says nothing, because the number
    alone is what caused the original misdiagnosis.
    """
    text = str(message or "")
    for name, pattern in (("schema", SCHEMA), ("key", KEY), ("quota", QUOTA),
                          ("model", MODEL), ("network", NETWORK)):
        if pattern.search(text):
            return name
    if code in (1007, 1008, 1011):
        return "other"
    return "other"


def explain(message: str, code: int | None = None) -> str:
    """One sentence the owner can act on, for the activity log."""
    what = kind(message, code)
    if what == "schema":
        index = rejected_declaration(message)
        which = f"declaration {index}" if index is not None else "one declaration"
        return (f"the server rejected my tool list ({which}). That is a schema fault, "
                f"not your API key — I will not ask you for one.")
    if what == "key":
        return "the API key was refused by the provider — please re-enter it."
    if what == "quota":
        return ("the provider says the quota is used up — I will step down the model "
                "ladder and try again.")
    if what == "model":
        return "the provider does not offer that model to this key — stepping down."
    if what == "network":
        return "the connection failed — retrying with a longer wait."
    return f"the session closed and the reason was not one I recognise: {str(message)[:160]}"
