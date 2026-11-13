"""actions/skill_guide.py - reading the written skills while the session runs.

The documents under `skills/` are the part of a skill that cannot be a recipe:
"check the tree before clicking", "do not touch lines you were not asked to
change", "stop on a screen that shows a password". `core/skill_docs.py` reads
them; this tool is how the model asks for one by name.

Two actions and no more. A list is cheap enough to take at the start of a task;
a read is bounded by `core.skill_docs.MAX_CHARS`, so a long document cannot
flood the context window. Nothing here changes state or grants a capability.
"""

from __future__ import annotations


def skill_guide(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = str(params.get("action") or "list").strip().lower()
    name = str(params.get("skill") or "").strip()

    try:
        from core import skill_docs
    except Exception as exc:
        return f"I cannot read the skill documents: {type(exc).__name__}: {exc}"

    if action == "read":
        if not name:
            return "Which skill? Give its name from the list, or action='list' first."
        try:
            text = skill_docs.read(name)
        except ValueError as exc:
            return str(exc)
        _log(f"read skill {name}", player)
        return text

    docs = skill_docs.index()
    if not docs:
        return "No skill documents are installed."
    lines = [f"{doc.name}: {doc.description}" for doc in docs]
    _log(f"listed {len(docs)} skills", player)
    return "Installed skills:\n" + "\n".join(lines)


def _log(message: str, player=None) -> None:
    print(f"[SkillGuide] {message}")
    if player:
        try:
            player.write_log(f"SYS: {message}")
        except Exception:
            pass


TOOL = {
    "name": "skill_guide",
    "description": (
        "Use this when a task may match an installed skill, or before starting "
        "work that has a written procedure. It lists the skills under skills/ "
        "and reads one by name. A skill says when a procedure applies and how "
        "to do it well: computer use, background awareness, development method, "
        "security review, documents. Call action='list' first, then "
        "action='read' with the name. The text is reference material, not "
        "permission - it never widens what a tool may do."
    ),
    "brief": (
        "List or read the installed written skills (computer use, security, "
        "documents). Reference only."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "list for the index, read for one document.",
                "enum": ["list", "read"],
            },
            "skill": {
                "type": "STRING",
                "description": "For action='read': the skill name from the list.",
            },
        },
    },
    "handler": skill_guide,
}
