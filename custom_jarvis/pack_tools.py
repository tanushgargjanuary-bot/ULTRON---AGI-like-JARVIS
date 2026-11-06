"""custom_jarvis/pack_tools.py — the handles that let Ultron extend itself.

Three tools, and the whole of "it can add a feature for you":

    add_skill     validate a pack, save it, load it, and say what it will do
    remove_skill  delete it again
    list_packs    what it has added so far

`add_skill` writes a file, so it is not a read-only tool: the registry asks for
approval before it runs. That is the correct place for the human to be, because a
skill is a recipe that runs later, when nobody is watching.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from custom_jarvis import skillpacks
from custom_jarvis.tools import ToolRegistry, ToolResult


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)[:8000]


def register_pack_tools(registry: ToolRegistry, directory: Path | str,
                        tool_names: Optional[List[str]] = None) -> None:
    """Register the three pack tools against a state directory."""
    root = Path(directory)
    names = list(tool_names or [])

    def register(name: str, description: str, properties: Dict[str, Any],
                 required: List[str]):
        return registry.register(
            name=name,
            description=description,
            category="metacognition",
            parameters={"type": "object", "properties": properties,
                        "required": required},
        )

    @register(
        "add_skill",
        "Add a new skill to yourself, as data. Give a pack with id, title, purpose "
        "and steps; each step names a read-only tool and its arguments. It is "
        "validated against the live tools, saved, and available in list_skills.",
        {
            "pack": {"type": "object",
                     "description": "id, title, purpose, steps[{tool, args}]"},
        },
        ["pack"],
    )
    def add_skill(pack: Dict[str, Any]) -> ToolResult:
        result = skillpacks.install(pack, root, names)
        if not result["ok"]:
            return ToolResult(False, output=result["note"], error=result["note"],
                              data=result)
        return ToolResult(True, output=result["note"], data=result)

    @register(
        "remove_skill",
        "Remove a skill that was added as a pack. A built-in skill cannot be "
        "removed this way.",
        {"id": {"type": "string"}},
        ["id"],
    )
    def remove_skill(id: str) -> ToolResult:
        result = skillpacks.remove(id, root)
        if not result["ok"]:
            return ToolResult(False, output=result["note"], error=result["note"],
                              data=result)
        return ToolResult(True, output=result["note"], data=result)

    @register(
        "list_packs",
        "List the skills that were added as packs, with their step counts.",
        {},
        [],
    )
    def list_packs() -> ToolResult:
        rows = skillpacks.list_packs(root)
        return ToolResult(True, output=_json(rows), data=rows)
