"""The minds Ultron thinks with, reachable by voice.

    "Show me your philosophy."                -> action "show"
    "Be more like Rick."                      -> action "adopt", voice "rick"
    "Mix Tony Stark and Rick, sixty forty."   -> action "blend", weights "rick 60 stark 40"
    "What can the Ultron voice do?"           -> action "abilities", voice "ultron"
    "Go back to the mind you shipped with."   -> action "reset"

The rules live in `core/philosophy.py`; this file only carries the conversation and
makes sure the owner is told, in plain words, what changed and what was held down.

Two things it will not do. It will not let the adversary voice become the majority of
the mind — that is refused with the reason, not argued about. And it will not quietly
drop a voice the owner named: every adjustment is reported in the same answer,
because a system that changes something the owner did not ask for is a system that
has stopped being predictable.
"""

from __future__ import annotations

import re

from core import failures, philosophy

# An owner will say the mix three ways: "rick 40, stark 60", "rick=40 stark=60", and
# "60% Rick and 40% Stark". One rule covers all three, and it does not need the words
# in any particular order: **every number belongs to the nearest name**, measured in
# characters, and the near edge of a name counts — so "Iron Man 50" lands on Stark,
# and "60% Rick and 40% Stark" splits correctly because Rick is nearer to 60.
_NUMBER = re.compile(r"\d+(?:\.\d+)?%?")


def _say(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line)


def _number(word: str) -> float | None:
    """A share in a token, or None. '40', '0.4' and '40%' read; '9000' does not.

    The range check is what keeps HAL's number out of the arithmetic: "HAL 9000" is
    a name, and 9000 is not a share of anybody's mind.
    """
    found = re.fullmatch(r"\d+(?:\.\d+)?", word.rstrip("%"))
    if not found:
        return None
    value = float(found.group(0))
    return value if 0.0 <= value <= 100.0 else None


def _names_in(text: str) -> list[tuple[int, int, str]]:
    """(first character, last character, key) for every name written in the text."""
    found: list[tuple[int, int, str]] = []
    low = text.lower()
    for spelling, key in philosophy.spellings():
        pattern = rf"(?<![a-z0-9]){re.escape(spelling)}(?![a-z0-9])"
        for match in re.finditer(pattern, low):
            found.append((match.start(), match.end() - 1, key))
    return found


def _numbers_in(text: str) -> list[tuple[int, int, float]]:
    """(first character, last character, share) for every usable number."""
    found: list[tuple[int, int, float]] = []
    for match in _NUMBER.finditer(text):
        value = _number(match.group(0))
        if value is not None:
            found.append((match.start(), match.end() - 1, value))
    return found


def _gap(name: tuple[int, int, str], number: tuple[int, int, float]) -> tuple[int, int]:
    """Distance from a name to a number, and which side it was on.

    The second number is the tie-break, and it is not decoration: in "rick 40 stark
    60" both names are two characters from a number, and the only thing that says
    which is which is that a share is written *after* the name it belongs to. Ties
    go to the number on the right.
    """
    if number[1] < name[0]:
        return (name[0] - number[1], 1)
    if number[0] > name[1]:
        return (number[0] - name[1], 0)
    return (0, 0)


def _parse_weights(text: str) -> dict[str, float]:
    """Pull names and numbers out of a spoken blend, in whatever order."""
    numbers = _numbers_in(str(text or ""))
    if not numbers:
        return {}
    found: dict[str, float] = {}
    closest: dict[str, tuple[int, int]] = {}
    for name in _names_in(str(text or "")):
        nearest = min(numbers, key=lambda number: _gap(name, number))
        distance = _gap(name, nearest)
        if distance < closest.get(name[2], (10 ** 6, 9)):
            closest[name[2]] = distance
            found[name[2]] = nearest[2]
    return found


def _cast_names() -> str:
    return ", ".join(voice.name for voice in philosophy.VOICES.values())


def _list(_parameters=None) -> str:
    return _say([
        "I can think with any of these, alone or mixed:",
        philosophy.catalogue(),
        "Mixed is better than switched. Say the mix, or say a name and I will use it "
        "as the strongest voice.",
    ])


def _show(_parameters=None) -> str:
    return _say([
        f"My mind right now: {philosophy.shares()}.",
        "",
        "This is what is added to my instruction when a session starts:",
        philosophy.prompt_block(),
        "",
        "The voices change how I answer and what I check first. They do not change "
        "what I am allowed to do.",
    ])


def _unknown(name: str) -> str:
    return f"I do not have a mind called '{name}'. I have: {_cast_names()}."


def _adopt(parameters: dict) -> str:
    name = str(parameters.get("voice") or parameters.get("name") or "").strip()
    if not name:
        return "Which mind? I have: " + _cast_names() + "."
    key = philosophy.resolve(name)
    if key is None:
        return _unknown(name)
    chosen, notes = philosophy.save_blend({key: parameters.get("weight", 0.6)})
    return _say([
        f"Done. My mind is now {philosophy.shares(chosen)}.",
        philosophy.VOICES[key].maxim,
        *notes,
        "Everything I am allowed to do is unchanged.",
    ])


def _blend(parameters: dict) -> str:
    text = str(parameters.get("weights") or parameters.get("voice") or "").strip()
    if not text:
        return ("Say the mix, for example 'Rick 40, Stark 40, Jarvis 20'. Each "
                "number is that mind's share of the whole.")
    wanted = _parse_weights(text)
    if not wanted:
        return (f"I could not find a mind and a number in '{text}'. Say it as "
                f"'name number', for example 'Rick 40'.")
    chosen, notes = philosophy.save_blend(wanted)
    return _say([f"Done. My mind is now {philosophy.shares(chosen)}.", *notes,
                 "Everything I am allowed to do is unchanged."])


def _abilities(parameters: dict) -> str:
    name = str(parameters.get("voice") or parameters.get("name") or "").strip()
    if not name:
        rows = []
        for key in philosophy.VOICES:
            voice = philosophy.VOICES[key]
            rows.append(f"  {voice.name}: " +
                        "; ".join(move.split(":", 1)[0] for move in voice.moves))
        return _say(["What each mind brings to the tools already here:", *rows,
                     "A method, not a permission: every one of these uses a tool "
                     "that was already here, through the same gate."])
    key = philosophy.resolve(name)
    if key is None:
        return _unknown(name)
    return _say([philosophy.describe(key), "",
                 "A method, not a permission: every one of these uses a tool that "
                 "was already here, through the same gate."])


def _reset(_parameters=None) -> str:
    philosophy.reset()
    return (f"Back to the mind I shipped with: {philosophy.shares()}. "
            f"Nothing else changed.")


def _rules(_parameters=None) -> str:
    return _say([
        philosophy.CHARTER,
        philosophy.TIE_BREAK,
        f"A blend keeps at most {philosophy.MAX_VOICES} voices, because the "
        f"instruction is paid for on every request.",
        "The adversary voice is held at 40% or less. It can sharpen an argument; it "
        "cannot be the majority of the mind that decides what to do.",
        "No voice adds a permission. Every method above uses a tool that was already "
        "here, under the same confirmations and the same limits.",
    ])


ACTIONS = {
    "list": _list, "voices": _list, "cast": _list,
    "show": _show, "current": _show, "status": _show,
    "adopt": _adopt, "be": _adopt, "choose": _adopt,
    "blend": _blend, "mix": _blend,
    "abilities": _abilities, "methods": _abilities, "can": _abilities,
    "reset": _reset, "default": _reset,
    "rules": _rules, "bounds": _rules,
}


def philosophy_tool(parameters: dict) -> str:
    """Answer one call. Every branch returns a sentence, because this is read aloud."""
    parameters = dict(parameters or {})
    name = str(parameters.get("action") or "show").strip().lower()
    handler = ACTIONS.get(name)
    if handler is None:
        return (f"I do not know the action '{name}'. I can: show, list, adopt, blend, "
                f"abilities, reset, rules.")
    try:
        return handler(parameters)
    except ValueError as error:
        # A refusal is the answer, not a crash: the reason is written to be said.
        return str(error)
    except Exception as error:
        failures.note("philosophy.philosophy_tool", error)
        return "That did not work, and I have recorded why. My mind is unchanged."


TOOL = {
    "name": "philosophy",
    "description": (
        "The minds Ultron thinks with, drawn from fictional scientists and robots: "
        "the butler's judgement, the engineer's proof, the scientist's doubt, the "
        "adversary's red team, the guardian's plain words. Use this tool when the "
        "user asks what Ultron's philosophy is, asks to think more like a named "
        "character, asks to mix several, asks what those minds can do, or asks to go "
        "back to the default. It changes manner and priority only; it never changes "
        "what Ultron is permitted to do."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "show (the blend in force), list (the cast), adopt (one voice "
                    "becomes the strongest), blend (set the proportions), abilities "
                    "(what a voice brings), reset (back to the shipped mind), rules "
                    "(the bounds that hold whatever the blend)."
                ),
                "enum": ["show", "list", "adopt", "blend", "abilities", "reset",
                         "rules"],
            },
            "voice": {
                "type": "STRING",
                "description": "The name the user said, as they said it.",
            },
            "weight": {
                "type": "NUMBER",
                "description": "Share of the mind for 'adopt', 0 to 1. Default 0.6.",
            },
            "weights": {
                "type": "STRING",
                "description": ("For 'blend': names and numbers as the user said "
                                "them, for example 'rick 40, stark 40, jarvis 20'."),
            },
        },
        "required": ["action"],
    },
    "handler": philosophy_tool,
}
