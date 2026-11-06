"""custom_jarvis/skillpacks.py — Ultron writes new skills itself, as data.

The limit that makes this safe is simple: **a pack is data, not code.** A pack is
a JSON file that names existing tools and the arguments to give them. It cannot
add a tool, cannot run Python, cannot reach the network on its own, and cannot
touch a path outside the workspace. So the worst a bad pack can do is call a
read-only tool with a silly argument — which is a bad recipe, not a breach.

What a pack may contain:

    id        lowercase, 3-40 characters, letters, digits and underscore
    title     one line, shown by `list_skills`
    purpose   one sentence: what it is for and why it exists
    steps     1-8 of {"tool": "<read-only tool>", "args": {...}}

What is refused, and why:

- **a tool that writes.** Packs are read-only in this build. A recipe that writes
  files and that the machine wrote for itself is a loop with no one in it.
- **a built-in id.** A pack can never shadow a reviewed recipe.
- **an absolute path, or `..`.** A skill runs inside the selected folder.
- **an argument the tool does not declare.** The tool's own schema is the check,
  so a typo is caught before the pack is saved, not at step three of five.

Every pack is written atomically, keeps the previous file as `.bak`, and can be
removed with one call. `load()` reads the folder at startup, which is how Ultron
remembers a skill it added for you yesterday.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from custom_jarvis.addon_runtime import INSPECTION_TOOLS
from custom_jarvis.skills import SKILL_BY_ID, Skill, register, unregister

FOLDER = "skills"
MAX_STEPS = 8
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,39}$")

# A pack may only use tools that read. This is the whole safety story, so it is
# one line rather than a policy engine.
ALLOWED = frozenset(INSPECTION_TOOLS)


def _clean(value: Any, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def validate(pack: Any, tool_names: Iterable[str] = ()) -> list[str]:
    """Every reason this pack must not be installed. Empty list means it is sound."""
    if not isinstance(pack, dict):
        return ["A pack must be a JSON object."]
    problems = []
    identity = _clean(pack.get("id"), 40)
    if not ID_PATTERN.match(identity):
        problems.append("id must be lowercase, start with a letter, and be 3-40 "
                        "characters of letters, digits and underscore")
    elif identity in SKILL_BY_ID:
        problems.append(f"'{identity}' is already a skill, so a pack cannot take it")
    if not _clean(pack.get("title"), 80):
        problems.append("title is required (one line)")
    if not _clean(pack.get("purpose")):
        problems.append("purpose is required (one sentence)")

    steps = pack.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("steps must be a non-empty list")
        return problems
    if len(steps) > MAX_STEPS:
        problems.append(f"a pack may have at most {MAX_STEPS} steps, not {len(steps)}")

    known = set(tool_names or ())
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            problems.append(f"step {index} must be an object with 'tool' and 'args'")
            continue
        tool = _clean(step.get("tool"), 60)
        if not tool:
            problems.append(f"step {index} has no tool")
            continue
        if tool not in ALLOWED:
            problems.append(f"step {index} uses '{tool}', which is not a read-only tool")
        elif known and tool not in known:
            problems.append(f"step {index} uses '{tool}', which this build does not have")
        args = step.get("args", {})
        if not isinstance(args, dict):
            problems.append(f"step {index}: args must be an object")
            continue
        for key, value in args.items():
            if not isinstance(value, (str, int, float, bool)):
                problems.append(f"step {index}: argument '{key}' must be a plain value")
                continue
            if key in ("path", "search_path") and isinstance(value, str):
                text = value.strip()
                if text.startswith("@") and text not in ("@workspace", "@target"):
                    problems.append(f"step {index}: '{text}' is not @workspace or @target")
                elif not text.startswith("@") and (
                        Path(text).is_absolute() or ".." in Path(text).parts):
                    problems.append(f"step {index}: a path must stay inside the workspace")
    return problems


def to_skill(pack: dict) -> Skill:
    """Turn a validated pack into the same `Skill` object a built-in is."""
    calls = tuple(
        (str(step["tool"]), {str(k): v for k, v in (step.get("args") or {}).items()})
        for step in pack["steps"]
    )
    return Skill(str(pack["id"]).strip(), _clean(pack.get("title"), 80),
                 _clean(pack.get("purpose")), calls)


def folder(directory: Path | str) -> Path:
    path = Path(directory) / FOLDER
    path.mkdir(parents=True, exist_ok=True)
    return path


def install(pack: Any, directory: Path | str, tool_names: Iterable[str] = ()) -> dict:
    """Validate, save and make a pack available. Returns a result the tool can read."""
    problems = validate(pack, tool_names)
    if problems:
        return {"ok": False, "id": _clean((pack or {}).get("id") if isinstance(pack, dict)
                                          else "", 40),
                "problems": problems,
                "note": "I did not save that pack: " + "; ".join(problems)}
    identity = str(pack["id"]).strip()
    target = folder(directory) / f"{identity}.json"
    try:
        if target.exists():
            target.with_suffix(".json.bak").write_text(
                target.read_text(encoding="utf-8"), encoding="utf-8")
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(pack, indent=2, ensure_ascii=False),
                             encoding="utf-8")
        os.replace(temporary, target)
    except OSError as error:
        return {"ok": False, "id": identity, "problems": [str(error)],
                "note": f"I could not save the pack: {error}"}

    added = register(to_skill(pack))
    return {"ok": True, "id": identity, "problems": [], "path": str(target),
            "note": (f"Saved '{identity}' with {len(pack['steps'])} step(s). "
                     "It is in `list_skills` now." if added else
                     "The file is saved, but the skill was already loaded in this "
                     "session, so it starts working after a restart.")}


def remove(identity: str, directory: Path | str) -> dict:
    """Delete a pack's file and unload it. A built-in is never touched."""
    name = _clean(identity, 40)
    path = folder(directory) / f"{name}.json"
    if not path.exists():
        return {"ok": False, "note": f"There is no pack called '{name}'."}
    try:
        path.unlink()
    except OSError as error:
        return {"ok": False, "note": f"I could not delete the pack: {error}"}
    unregister(name)
    return {"ok": True, "note": f"Removed the pack '{name}'."}


def list_packs(directory: Path | str) -> list[dict]:
    """What is installed: id, title, steps, and the file it came from."""
    rows = []
    for path in sorted(folder(directory).glob("*.json")):
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(pack, dict):
            continue
        rows.append({"id": _clean(pack.get("id"), 40),
                     "title": _clean(pack.get("title"), 80),
                     "steps": len(pack.get("steps") or []),
                     "file": path.name})
    return rows


def load(directory: Path | str, tool_names: Iterable[str] = ()) -> dict:
    """Load every pack in the folder. Returns what loaded and what did not."""
    loaded, errors = [], {}
    for path in sorted(folder(directory).glob("*.json")):
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors[path.name] = f"not valid JSON: {error}"
            continue
        problems = validate(pack, tool_names)
        if problems:
            errors[path.name] = "; ".join(problems)
            continue
        if register(to_skill(pack)):
            loaded.append(str(pack["id"]).strip())
        else:
            errors[path.name] = "that id is already loaded"
    return {"loaded": loaded, "errors": errors}
