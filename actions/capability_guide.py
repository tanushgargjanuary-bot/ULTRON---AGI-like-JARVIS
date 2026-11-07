"""Map a user's goal to existing tools and skills, including common synonyms."""

from __future__ import annotations

import re

from core import tool_catalog
from custom_jarvis.skills import SKILLS


# Small deterministic vocabulary keeps this lookup fast and useful when the user
# describes an outcome instead of knowing the tool's name.
ALIASES = {
    "compress": {"compress", "compression", "zip", "archive", "shrink", "reduce", "smaller"},
    "convert": {"convert", "conversion", "transform", "format"},
    "search": {"search", "find", "look", "locate"},
    "summarize": {"summarize", "summary", "digest", "overview"},
    "screenshot": {"screenshot", "capture", "screen", "snapshot"},
    "transcribe": {"transcribe", "transcription", "speech", "audio"},
    "evolve": {"evolve", "evolution", "self_modify", "self_change", "improve", "upgrade"},
    "compress": {"compress", "compression", "zip", "archive", "shrink", "reduce", "smaller", "large"},
    "document": {"document", "pdf", "word", "text", "file"},
}


def _terms(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9_+#.-]+", text.lower())
        if len(word) > 2
    }


def _expand(query: set[str]) -> set[str]:
    expanded = set(query)
    for family, terms in ALIASES.items():
        if query.intersection(terms):
            expanded.update(terms)
            expanded.add(family)
    return expanded


def _score(query: set[str], text: str) -> int:
    words = _terms(text)
    matched = query.intersection(words)
    # Ignore generic request words so a weak match is not presented as a fit.
    matched.difference_update({"file", "document", "help", "need", "want", "make", "please"})
    return 3 * len(matched)


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Match a stated goal to live tools and skills; never installs or edits code."""
    request = str(parameters.get("request") or "").strip()
    if not request:
        return "Tell me what you are trying to get done, and I will map it to my tools."

    query = _expand(_terms(request))
    try:
        entries = tool_catalog.build()
    except Exception as exc:
        return f"I could not read my live tool catalog: {exc}"

    tool_hits = []
    for entry in entries:
        score = _score(query, f"{entry.name} {entry.category} {entry.summary}")
        if score:
            tool_hits.append((score, entry))
    tool_hits.sort(key=lambda item: (-item[0], not item[1].available, item[1].name))

    skill_hits = []
    for skill in SKILLS:
        score = _score(query, f"{skill.identity} {skill.title} {skill.purpose}")
        if score:
            skill_hits.append((score, skill))
    skill_hits.sort(key=lambda item: (-item[0], item[1].identity))

    lines = [f"For “{request}”:"]
    # A single shared generic term is not enough to recommend an ability.
    tool_hits = [hit for hit in tool_hits if hit[0] >= 3]
    skill_hits = [hit for hit in skill_hits if hit[0] >= 3]

    if tool_hits:
        lines.append("Tools: " + "; ".join(
            f"{entry.name} ({'ready' if entry.available else 'unavailable: ' + entry.reason})"
            for _, entry in tool_hits[:5]
        ) + ".")
    else:
        lines.append("No strong tool match. I checked the live tool catalog.")

    if skill_hits:
        lines.append("Skills: " + "; ".join(
            f"{skill.title} [{skill.identity}]" for _, skill in skill_hits[:5]
        ) + ".")
    else:
        lines.append("No strong skill match in my installed skill recipes.")

    if not tool_hits:
        lines.append(
            "The next step is to research candidate GitHub projects, inspect their "
            "fit and risks, then propose one bounded native change. I do not install "
            "repository code automatically."
        )
    lines.append(
        "I can evolve my own source through self_modify: propose a change, rehearse "
        "it in a copy, confirm in two different places, then apply. I should compare "
        "the same task before and after, keep only a demonstrated improvement, and "
        "restart before claiming the change is active."
    )
    return "\n".join(lines)


TOOL = {
    "name": "capability_guide",
    "description": (
        "Map a task to Ultron's live tools and installed skills. Use when the user "
        "does not know which ability could help, describes being stuck, asks whether "
        "Ultron can do something, or asks how Ultron can improve itself. This reports "
        "capabilities and gaps; it does not install code."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "request": {
                "type": "STRING",
                "description": "The task or capability the user wants to accomplish."
            }
        },
        "required": ["request"],
    },
    "handler": run,
}
