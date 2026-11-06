"""custom_jarvis/ship_tools.py — the four handles for shipping and updating.

    ship_status    what would be shipped, and is the tree safe to publish
    ship_now       scan, check, commit, push — asks first, because it publishes
    check_update   is there a newer version on the remote, and what does it touch
    apply_update   pull it, verify it, reload what is safe, ask for a restart if needed

`ship_now` and `apply_update` change something outside this machine, so neither is
in the read-only set: the registry asks the owner before either runs. That is the
right place for the human, because a push is public and an update is the code
that will run tomorrow.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, List, Optional

from custom_jarvis.selfupdate import Updater
from custom_jarvis.ship import Shipper, describe, token_from_environment
from custom_jarvis.tools import ToolRegistry, ToolResult


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)[:8000]


def _verify(repo: Path) -> Callable[[], dict]:
    """A cheap, real check for a pulled version: every .py file must parse."""
    def run() -> dict:
        broken = []
        count = 0
        for path in sorted(repo.rglob("*.py")):
            if any(part in {"__pycache__", ".venv", ".git"} for part in path.parts):
                continue
            count += 1
            try:
                compile(path.read_text(encoding="utf-8", errors="replace"), str(path), "exec")
            except SyntaxError as error:
                broken.append(f"{path.name}:{error.lineno}")
        return {"ok": not broken, "count": count,
                "note": (f"{count} modules parse." if not broken
                         else "these did not parse: " + ", ".join(broken[:5]))}
    return run


def register_ship_tools(registry: ToolRegistry, repo: Path | str,
                        pending_path: Path | str | None = None) -> None:
    root = Path(repo)
    pending_file = Path(pending_path) if pending_path else root / "ship_pending.json"

    def pending() -> List[dict]:
        try:
            rows = json.loads(pending_file.read_text(encoding="utf-8"))
            return rows if isinstance(rows, list) else []
        except (OSError, ValueError):
            return []

    def clear_pending() -> None:
        try:
            pending_file.write_text("[]", encoding="utf-8")
        except OSError:
            pass

    def register(name: str, description: str, properties: dict, required: list):
        return registry.register(
            name=name, description=description, category="shipping",
            parameters={"type": "object", "properties": properties,
                        "required": required})

    @register(
        "ship_status",
        "What would be shipped to GitHub right now: the changed files, whether the "
        "tree contains a secret, whether the ignore rules still hold, and any "
        "change that was made and is waiting to be shipped.",
        {},
        [],
    )
    def ship_status() -> ToolResult:
        shipper = Shipper(root, token_from_environment())
        report = shipper.status()
        scan = shipper.scan()
        report.update({"scan": {"files": scan["files"], "clean": scan["clean"],
                                "hits": scan["hits"][:5]},
                       "guards": shipper.guards(), "pending": pending()})
        return ToolResult(True, output=_json(report), data=report)

    @register(
        "ship_now",
        "Ship the current work to GitHub: scan for secrets, check the ignore rules, "
        "check that changed files parse, commit with a message that says why, and "
        "push fast-forward only. Requires approval because it publishes.",
        {"message": {"type": "string", "description": "What changed, in one line"},
         "why": {"type": "string", "description": "Why it changed"}},
        ["message"],
    )
    def ship_now(message: str, why: str = "") -> ToolResult:
        shipper = Shipper(root, token_from_environment(),
                          log_path=root / ".git" / "ultron-ship-log.json")
        result = shipper.ship(message, why=why)
        if result.get("ok"):
            clear_pending()
        return ToolResult(bool(result.get("ok")), output=describe(result),
                          error="" if result.get("ok") else describe(result),
                          data=result)

    @register(
        "check_update",
        "Check whether GitHub has a newer version than this copy, and which files "
        "it changes. Reads only: nothing is applied.",
        {},
        [],
    )
    def check_update() -> ToolResult:
        updater = Updater(root, token_from_environment())
        result = updater.check()
        return ToolResult(True, output=_json(result), data=result)

    @register(
        "apply_update",
        "Update this copy from GitHub: pull fast-forward only, verify that every "
        "module parses, reload skill packs and the tool catalog, and say whether a "
        "restart is needed. A failed verification is reverted. Requires approval.",
        {},
        [],
    )
    def apply_update() -> ToolResult:
        reload_hooks = []

        def reload_skills() -> dict:
            from custom_jarvis import skillpacks
            from custom_jarvis.skills import SKILLS
            return {"ok": True, "skills": len(SKILLS),
                    "note": "skill packs are read from disk on demand"}

        reload_hooks.append(reload_skills)
        updater = Updater(root, token_from_environment(), reload_hooks=reload_hooks)
        result = updater.apply(verify=_verify(root))
        return ToolResult(bool(result.get("ok")), output=_json(result),
                          error="" if result.get("ok") else str(result.get("note", "")),
                          data=result)
