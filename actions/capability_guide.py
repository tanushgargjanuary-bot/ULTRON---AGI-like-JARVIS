"""Point a user's goal at tools and skills Ultron already has."""

from __future__ import annotations

import re
from pathlib import Path

from core import tool_catalog
from custom_jarvis.skills import SKILLS


def _terms(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9_+#.-]+", text.lower())
            if len(word) > 2}


def _score(query: set[str], text: str) -> int:
    words = _terms(text)
    return sum(3 if word in words else 0 for word in query)


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Match a stated goal to current tools/skills; never installs or edits code."""
    request = str(parameters.get("request") or "").strip()
    if not request:
        return "Tell me what you are trying to get done, and I will map it to my tools."
    query = _terms(request)
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
    if tool_hits:
        lines.append("Tools: " + "; ".join(
            f"{e.name} ({'ready' if e.available else 'unavailable: ' + e.reason})"
            for _, e in tool_hits[:5]) + ".")
    else:
        lines.append("No strong tool-name match. I checked the live tool catalog.")

    if skill_hits:
        lines.append("Skills: " + "; ".join(
            f"{s.title} [{s.identity}]" for _, s in skill_hits[:5]) + ".")
    else:
        lines.append("No strong skill match in my installed skill recipes.")

    if not tool_hits:
        lines.append(
            "I can investigate a GitHub repository for a missing capability, then "
            "propose a native implementation. I do not download or install repository "
            "code automatically.")
    lines.append(
        "I can evolve my own source through self_modify: propose, rehearse in a copy, "
        "confirm in two different places, then apply. A source change takes effect "
        "after restart.")
    return "\n".join(lines)


TOOL = {
    "name": "capability_guide",
    "description": (
        "Map a task to Ultron's existing tools and skills. Use when the user is "
        "unsure whether Ultron can do a task, seems stuck, asks what tool could help, "
        "or asks how Ultron can improve itself. This reports capabilities and gaps; "
        "it does not install code."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "request": {
                "type": "STRING",
                "description": "The task the user wants to accomplish or capability they need."
            }
        },
        "required": ["request"],
    },
    "handler": run,
}
