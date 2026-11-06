"""How a tool is described to the model — and what makes it ever get called.

The owner asked the question this module exists for:

    "they need a condition to get triggered, otherwise ULTRON will never use them"

A declaration says a tool exists. A description says what it does. Neither of those
is a reason to call it, and a model given a list of abilities with no conditions
will use the three it already knows. So each capability line in the instruction
leads with its CONDITION:

    - reasoning: Use it before any multi-step task. — Ultron's own reasoning kernel…

The sentence is taken from the tool's own description, never written here, so a tool
cannot be described in one place and triggered from another. The bug this fixed was
in the old builder: it cut the first 150 characters of the description, and on this
build 10 of 32 tools had their condition entirely past that cut. The capability
survived and the trigger did not — reasoning, curriculum, philosophy, self_modify and
recall_memory among them.

Pure functions on purpose: no import of main.py, no session, no settings. The proof
gate and the tests call these directly instead of compiling a slice of the app.
"""

from __future__ import annotations

from core import failures

# What a sentence has to contain to count as a condition rather than a description.
# This is wording the tools already use; nothing here asks a tool to be rephrased.
CONDITION_CUES = (
    "use this when", "use it when", "use when", "use this tool when",
    "use whenever", "use it whenever", "use it before", "use this for",
    "use it for", "use for", "when the user", "whenever the user",
    "when you", "whenever you", "when someone", "call it when", "call this when",
    "call it whenever", "called when", "must be called when",
    "reach for this when", "use it instead", "use this instead",
)

LINE_CHARS = 150          # one capability line; the condition is never the part cut
CUT_AT = 60               # a cue later than this in a sentence starts the condition


def sentences(text: str) -> list[str]:
    """Split a description into sentences without pulling in a parser.

    Descriptions are short prose written by hand, so a full stop or a question mark
    followed by a space covers every case that occurs. An abbreviation that splits a
    sentence in two costs one line that reads slightly long, and nothing else.
    """
    pieces = text.replace("? ", "?\n").replace(". ", ".\n").split("\n")
    return [piece.strip() for piece in pieces if piece.strip()]


def condition_of(description: str) -> str:
    """The sentence that says WHEN to call the tool, or an empty string.

    The first sentence containing a cue wins. Deliberately simple: the alternative
    is a model, and a model inside the prompt builder would make the instruction
    differ between two launches of the same build.
    """
    for sentence in sentences(description):
        low = sentence.lower()
        at = min((low.find(cue) for cue in CONDITION_CUES if cue in low), default=-1)
        if at < 0:
            continue
        if at > CUT_AT:
            # Some descriptions open with the capability and reach the condition at
            # the end of the same long sentence. Cutting that from the front loses
            # the trigger again, so the condition starts at its cue.
            trimmed = sentence[at:]
            return trimmed[:1].upper() + trimmed[1:]
        return sentence
    return ""


def line(name: str, description: str) -> str:
    """`- name: when to call it — what it does`, capped at LINE_CHARS.

    The condition is first for one reason: the line is capped, so whatever comes
    last is what gets cut. Putting the trigger first means the cap can only ever
    cost a description, never a reason to call the tool.
    """
    text = " ".join(str(description or "").split())
    if not text:
        return f"- {name}"
    when = condition_of(text)
    what = sentences(text)[0] if sentences(text) else text
    if when:
        rendered = (f"- {name}: {when}" if when == what
                    else f"- {name}: {when} — {what}")
    else:
        rendered = f"- {name}: {what}"
    return rendered[:LINE_CHARS]


def describe(declarations) -> str:
    """Every declared tool, one line each, condition first."""
    lines = []
    for declaration in declarations or ():
        try:
            name = (declaration.get("name") if isinstance(declaration, dict)
                    else getattr(declaration, "name", None))
            description = (declaration.get("description")
                           if isinstance(declaration, dict)
                           else getattr(declaration, "description", "")) or ""
        except Exception as error:                          # noqa: BLE001
            # A malformed declaration is not a tool, but it is also not nothing: a
            # tool silently missing from the list is a feature the model cannot call.
            failures.note("tool_prompt.describe", error)
            continue
        if name:
            lines.append(line(name, description))
    return "\n".join(lines)


def with_condition(declarations) -> list[str]:
    """The tools whose rendered line carries no condition. Empty means all do."""
    return [declaration["name"] for declaration in declarations
            if not condition_of(str(declaration.get("description", "") ))]
