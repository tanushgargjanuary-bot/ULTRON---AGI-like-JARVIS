"""Map a user's goal to existing tools and skills, including common synonyms."""

from __future__ import annotations

import re

from core import tool_catalog
from custom_jarvis.skills import SKILLS


# Small deterministic vocabulary keeps this lookup fast and useful when the user
# describes an outcome instead of knowing the tool's name.
ALIASES = {
    "convert": {"convert", "conversion", "transform", "format"},
    "search": {"search", "find", "look", "locate"},
    "summarize": {"summarize", "summary", "digest", "overview"},
    "screenshot": {"screenshot", "capture", "screen", "snapshot"},
    "transcribe": {"transcribe", "transcription", "speech", "audio"},
    "evolve": {"evolve", "evolution", "self_modify", "self_change", "improve", "upgrade"},
    "compress": {"compress", "compression", "zip", "archive", "shrink", "reduce", "smaller", "oversized", "big"},
}


# Task cues bridge user outcomes to broad tool families. Availability always comes
# from the live catalog, so a cue cannot invent a capability.
TASK_TOOL_CUES = {
    "compress": {"file_processor"},
    "convert": {"file_processor"},
    "summarize": {"file_processor"},
    "transcribe": {"file_processor"},
    "screenshot": {"screen_process"},
    "search": {"web_search", "file_controller"},
    "evolve": {"self_modify"},
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
    # Tool and skill identifiers use underscores; let ordinary user wording
    # match those names without requiring users to know the internal spelling.
    for word in tuple(words):
        if "_" in word:
            words.update(_terms(word.replace("_", " ")))
    matched = query.intersection(words)
    # Ignore generic request words so a weak match is not presented as a fit.
    matched.difference_update({"file", "document", "help", "need", "want", "make", "please"})
    return 3 * len(matched)


def _query_for(request: str) -> set:
    """The search terms for a request, with the phrases that hide their own meaning."""
    lowered = request.lower()
    query = _expand(_terms(request))
    if any(phrase in lowered for phrase in (
        "too big to send", "too large to send", "file is too big", "file is too large",
        "make the file smaller", "make this file smaller",
    )):
        query.update(ALIASES["compress"])
    return query


def _tool_hits(query: set, expanded: set, entries) -> list:
    """Live tools that match, scored, with a family cue worth six points."""
    hits = []
    for entry in entries:
        score = _score(query, f"{entry.name} {entry.category} {entry.summary}")
        for family, names in TASK_TOOL_CUES.items():
            if expanded.intersection(ALIASES.get(family, {family})) and entry.name in names:
                score += 6
        if score:
            hits.append((score, entry))
    hits.sort(key=lambda item: (-item[0], not item[1].available, item[1].name))
    return hits


def _skill_hits(query: set) -> list:
    """Installed skill recipes that match, scored."""
    hits = []
    for skill in SKILLS:
        score = _score(query, f"{skill.identity} {skill.title} {skill.purpose}")
        if score:
            hits.append((score, skill))
    hits.sort(key=lambda item: (-item[0], item[1].identity))
    return hits


def _report(request: str, tool_hits: list, skill_hits: list) -> str:
    """The answer: what matched, what did not, and the honest next step."""
    lines = [f"For “{request}”:"]
    ready_hits = [hit for hit in tool_hits if hit[1].available]

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

    if not ready_hits:
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


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Match a stated goal to live tools and skills; never installs or edits code."""
    request = str(parameters.get("request") or "").strip()
    if not request:
        return "Tell me what you are trying to get done, and I will map it to my tools."

    query = _query_for(request)
    try:
        entries = tool_catalog.build()
    except Exception as exc:
        return f"I could not read my live tool catalog: {exc}"

    # A single shared generic term is not enough to recommend an ability.
    tool_hits = [hit for hit in _tool_hits(query, _expand(query), entries) if hit[0] >= 3]
    skill_hits = [hit for hit in _skill_hits(query) if hit[0] >= 3]
    return _report(request, tool_hits, skill_hits)


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
