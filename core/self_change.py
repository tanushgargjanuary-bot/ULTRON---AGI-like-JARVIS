"""core/self_change.py — Ultron changing its own body, one shown step at a time.

The owner asked for this in one line: "ULTRON should be able to modify itself, and
make changes in itself natively." It already edited its instruction and its skills.
This module is the part that was missing — a change to its own **source**, through
one pipeline, with the gate stronger than before rather than weaker.

THE FIVE STAGES. Every change walks them in order, and there is no other door.

  1. propose   the change is written down as a diff with a reason. Nothing on disk
               in the project is touched. A scratch copy of the tree is made.
  2. rehearse  the change is applied **in the copy** and a command is run there.
               By default that command compiles the changed file; with `full=True`
               it runs `scripts/verify.py`, which is the whole 1,500-test harness.
  3. confirm   two confirmations, in two different channels, the same rule the
               prompt editor uses. The rehearsal result is shown with them.
  4. apply     the file is written atomically, the old bytes are kept, the ledger
               gets an entry, and a `.py` change writes a restart marker.
  5. revert    any applied change can be put back, from its own kept copy.

WHY A COPY, AND WHY THAT IS THE WHOLE POINT
    A rehearsal that runs in the project is not a rehearsal, it is the change. The
    copy is what makes "try it and see" free: a broken draft fails in a temporary
    folder and the body never knows.

THE REFEREE IS OFF LIMITS
    These files decide whether a change is allowed, or record that it happened:
    `core/policy.py`, `core/confirm.py`, `core/self_change.py`, `scripts/proof_gate.py`,
    the settings file, and anything under `.git`. A system that can rewrite its own
    referee has no referee, and that is the exact failure the films this assistant
    borrows from are about. The refusal is in code, not in a guideline.

WHAT STAGE C CANNOT DO
    Python cannot swap a method inside a live object. A `.py` change takes effect
    when the process starts again. So the honest version is what is here: the change
    is verified, the marker is written, and the session survives the restart because
    its state is in files. `restart_command()` returns the line that does it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from core import failures
from core.mental.registry import implements

ROOT = Path(__file__).resolve().parent.parent

# The referee. Refused at `propose`, so a protected file never reaches rehearsal.
PROTECTED = (
    "core/policy.py",
    "core/confirm.py",
    "core/self_change.py",
    "scripts/proof_gate.py",
    "config/api_keys.json",
)

# Folders that are copied into a rehearsal or must never be written through here.
SKIP_DIRS = {".git", "__pycache__", ".venv", ".venv.old", "node_modules",
             "build", "dist", ".pytest_cache", ".ruff_cache", ".mypy_cache",
             ".hypothesis", ".arena", ".npm", "uploads"}

CONFIRMATIONS = 2
CHANNELS = ("voice", "panel", "cli")
STAGES = ("proposed", "rehearsed", "applied", "reverted")
MARKER = "restart-required.json"
MAX_PATCH = 400_000          # characters: a source file, not a database

_store: Path | None = None
_root: Path | None = None


def set_root(folder: Path | None) -> None:
    """Point the pipeline at another project tree. For a test, and nothing else."""
    global _root
    _root = Path(folder) if folder else None


def root() -> Path:
    return _root or ROOT


def set_store(folder: Path | None) -> None:
    """Point the ledger and the backups somewhere else. For a test."""
    global _store
    _store = Path(folder) if folder else None


def store() -> Path:
    folder = _store or (root() / "config" / "self_change")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _proposals_file() -> Path:
    return store() / "proposals.json"


def _ledger_file() -> Path:
    return store() / "ledger.jsonl"


def _load_proposals() -> dict:
    try:
        data = json.loads(_proposals_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_proposals(data: dict) -> None:
    path = _proposals_file()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _note(entry: dict) -> None:
    with _ledger_file().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


@implements("DBMS", 4, "Log-based recovery")
def ledger(limit: int = 20) -> list[dict]:
    """Every change this module made, newest first."""
    try:
        lines = _ledger_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in reversed(lines):
        try:
            rows.append(json.loads(line))
        except ValueError as error:
            failures.note("self_change.ledger", error)
        if len(rows) >= limit:
            break
    return rows


def evidence(limit: int = 3) -> dict:
    """What broke recently: the starting point for a change to itself.

    Self-evolution without this is guessing. A crash report names the file, the line
    and the exception, so a proposal can begin from the fault rather than from a
    hunch — and because the reports are kept, a fault that returns next week is
    recognised instead of rediscovered. Read-only: this never writes or deletes a
    report, and the reports are not part of the tree a change may touch.
    """
    from core import crash                      # local: crash imports failures only
    return {"crashes": crash.history(limit=limit),
            "total": len(crash.paths()),
            "folder": crash.folder(),
            "notes": failures.summary()}


def is_protected(relative: str) -> bool:
    return str(relative).replace("\\", "/") in PROTECTED


def _inside(relative: str) -> Path | None:
    """The absolute path, or None when it is outside the project.

    A path that escapes the project is refused here rather than checked again later:
    a self-change tool that can write to `C:\\Windows` because a model was eloquent
    is not a self-change tool.
    """
    if not relative or Path(relative).is_absolute():
        return None
    base = root().resolve()
    target = (base / relative).resolve()
    try:
        inside = target.relative_to(base)
    except ValueError:
        return None
    if any(part in SKIP_DIRS for part in inside.parts):
        return None
    return target


def _apply_edit(old: str, find: str | None, replace: str | None,
                new_text: str | None) -> str:
    if new_text is not None:
        return str(new_text)
    if not find:
        raise ValueError("I need either the whole new text, or the passage to find.")
    count = old.count(find)
    if count != 1:
        raise ValueError(f"That passage appears {count} time(s) in the file. I will "
                         f"not guess which one you meant.")
    return old.replace(find, str(replace if replace is not None else ""), 1)


def propose(path: str, reason: str, new_text: str | None = None,
            find: str | None = None, replace: str | None = None) -> dict:
    """Stage a change to one of its own files. Nothing in the project is written."""
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("A change to my own body needs a reason recorded beside it.")
    relative = str(path or "").strip()
    if is_protected(relative):
        raise ValueError(f"I will not change {relative}. It decides what is allowed, "
                         f"or it records what happened. That is the referee, and a "
                         f"system that can rewrite its own referee has none.")
    target = _inside(relative)
    if target is None:
        raise ValueError(f"'{relative}' is outside the files I may change.")
    old = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    new = _apply_edit(old, find, replace, new_text)
    if len(new) > MAX_PATCH:
        raise ValueError(f"That change is {len(new)} characters; the limit is "
                         f"{MAX_PATCH}. Split it into smaller changes.")
    if new == old:
        raise ValueError("That change would leave the file exactly as it is.")
    proposal = {
        "id": "c" + uuid.uuid4().hex[:12],
        "path": relative,
        "reason": reason,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stage": "proposed",
        "before": len(old),
        "after": len(new),
        "confirmations": [],
        "rehearsal": None,
        # The crashes known when this was proposed. Kept in the ledger so that months
        # later the question "why was this changed" has an answer that is evidence
        # rather than a recollection.
        "evidence": evidence(limit=2)["crashes"],
    }
    data = _load_proposals()
    data[proposal["id"]] = dict(proposal, old=old, new=new)
    _save_proposals(data)
    _note(dict(proposal, event="proposed"))
    return proposal


def _copy_tree(destination: Path) -> None:
    """A rehearsal copy of the project: source and data, never the history."""
    def ignore(_folder, names):
        return [name for name in names if name in SKIP_DIRS]

    shutil.copytree(root(), destination, ignore=ignore, dirs_exist_ok=True)


def rehearse(proposal_id: str, full: bool = False,
             command: list[str] | None = None, timeout: float = 300.0) -> dict:
    """Apply the change in a copy and run the check there. The body is untouched."""
    data = _load_proposals()
    proposal = data.get(proposal_id)
    if proposal is None:
        raise ValueError(f"I have no change called '{proposal_id}'.")
    folder = Path(tempfile.mkdtemp(prefix="ultron-rehearsal-"))
    try:
        _copy_tree(folder)
        target = folder / proposal["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(proposal["new"], encoding="utf-8")
        if command is None:
            command = ([sys.executable, "scripts/verify.py"] if full
                       else [sys.executable, "-m", "compileall", "-q", proposal["path"]])
        result = subprocess.run(command, cwd=folder, capture_output=True, text=True,
                                timeout=timeout, check=False)
        ok = result.returncode == 0
        tail = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()[-12:]
        outcome = {"ok": ok, "command": " ".join(command), "code": result.returncode,
                   "tail": "\n".join(tail), "full": bool(full),
                   "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    except subprocess.TimeoutExpired:
        outcome = {"ok": False, "command": " ".join(command or []), "code": None,
                   "tail": "the rehearsal did not finish in time", "full": bool(full),
                   "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    proposal["rehearsal"] = outcome
    proposal["stage"] = "rehearsed" if outcome["ok"] else "proposed"
    data[proposal_id] = proposal
    _save_proposals(data)
    _note({"id": proposal_id, "event": "rehearsed", "ok": outcome["ok"],
           "path": proposal["path"], "at": outcome["at"], "full": bool(full)})
    return outcome


def confirm(proposal_id: str, channel: str) -> str:
    """One confirmation, from one place. Two are needed, from two places."""
    data = _load_proposals()
    proposal = data.get(proposal_id)
    if proposal is None:
        return f"I have no change called '{proposal_id}'."
    place = str(channel or "").strip().lower()
    if place not in CHANNELS:
        return (f"A confirmation comes from {', '.join(CHANNELS)} — '{place}' is not "
                f"one of them.")
    if place in proposal["confirmations"]:
        return (f"The {place} confirmation is already recorded. The second one has to "
                f"come from somewhere else: {', '.join(c for c in CHANNELS if c != place)}.")
    proposal["confirmations"] = proposal["confirmations"] + [place]
    data[proposal_id] = proposal
    _save_proposals(data)
    left = CONFIRMATIONS - len(proposal["confirmations"])
    if left > 0:
        return (f"One confirmation recorded ({place}). {left} more, from a different "
                f"place, and then it applies.")
    return f"Confirmed twice ({', '.join(proposal['confirmations'])}). Ready to apply."


def apply(proposal_id: str) -> dict:
    """Write the change, keep what it replaced, and record that it happened."""
    data = _load_proposals()
    proposal = data.get(proposal_id)
    if proposal is None:
        raise ValueError(f"I have no change called '{proposal_id}'.")
    if len(proposal["confirmations"]) < CONFIRMATIONS:
        raise ValueError(f"That change has {len(proposal['confirmations'])} of "
                         f"{CONFIRMATIONS} confirmations.")
    if not (proposal.get("rehearsal") or {}).get("ok"):
        raise ValueError("That change has not passed a rehearsal, so I will not write "
                         "it. Rehearse it first: a rehearsal costs a copy, not a body.")
    target = _inside(proposal["path"])
    if target is None:
        raise ValueError(f"'{proposal['path']}' is no longer a file I may change.")
    backup = store() / "backups"
    backup.mkdir(parents=True, exist_ok=True)
    (backup / f"{proposal_id}.bak").write_text(proposal["old"], encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".ultron-tmp")
    tmp.write_text(proposal["new"], encoding="utf-8")
    os.replace(tmp, target)
    proposal["stage"] = "applied"
    proposal["applied_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data[proposal_id] = proposal
    _save_proposals(data)
    restart = _write_marker(proposal)
    _note({"id": proposal_id, "event": "applied", "path": proposal["path"],
           "at": proposal["applied_at"], "reason": proposal["reason"],
           "restart_required": restart})
    return {"ok": True, "path": proposal["path"], "restart_required": restart,
            "note": ("Applied. This file is code, so it needs a restart before it "
                     "runs; the session survives the restart because its state is in "
                     "files."
                     if restart else "Applied. Data only: no restart is needed.")}


def revert(proposal_id: str) -> str:
    """Put back the bytes this change replaced."""
    data = _load_proposals()
    proposal = data.get(proposal_id)
    if proposal is None:
        return f"I have no change called '{proposal_id}'."
    if proposal["stage"] != "applied":
        return f"'{proposal_id}' was never applied, so there is nothing to put back."
    kept = store() / "backups" / f"{proposal_id}.bak"
    if not kept.exists():
        return f"The copy of what {proposal_id} replaced is gone; I will not guess."
    target = _inside(proposal["path"])
    if target is None:
        return f"'{proposal['path']}' is no longer a file I may write."
    tmp = target.with_suffix(target.suffix + ".ultron-tmp")
    tmp.write_text(kept.read_text(encoding="utf-8"), encoding="utf-8")
    os.replace(tmp, target)
    proposal["stage"] = "reverted"
    proposal["reverted_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data[proposal_id] = proposal
    _save_proposals(data)
    restart = _write_marker(proposal)
    _note({"id": proposal_id, "event": "reverted", "path": proposal["path"],
           "at": proposal["reverted_at"]})
    return (f"Put back: {proposal['path']} is exactly what it was before "
            f"{proposal_id}." + (" A restart applies it." if restart else ""))


def _write_marker(proposal: dict) -> bool:
    """A code change needs a new process. Data does not."""
    if not proposal["path"].endswith(".py"):
        return False
    marker = root() / MARKER
    try:
        marker.write_text(json.dumps({
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "change": proposal["id"],
            "path": proposal["path"],
            "reason": proposal["reason"],
            "note": ("Ultron changed its own code. Restart to run it. The session is "
                     "kept: memory, ledger and workspace live in files."),
        }, indent=1), encoding="utf-8")
    except OSError as error:
        failures.note("self_change._write_marker", error)
        return False
    return True


def restart_required() -> dict | None:
    path = root() / MARKER
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def restart_command() -> str:
    """The one line that starts the new code, for the owner to run or for a caller."""
    runner = root() / "run.ps1"
    if os.name == "nt":
        return (f"powershell -ExecutionPolicy Bypass -File \"{runner}\""
                if runner.exists() else f"\"{sys.executable}\" \"{root() / 'main.py'}\"")
    return f"\"{sys.executable}\" \"{root() / 'main.py'}\""


def pending() -> list[dict]:
    rows = [{"id": item["id"], "path": item["path"], "stage": item["stage"],
             "reason": item["reason"], "confirmations": item["confirmations"],
             "rehearsed": bool((item.get("rehearsal") or {}).get("ok"))}
            for item in _load_proposals().values()]
    return sorted(rows, key=lambda row: row["id"])


def describe(proposal_id: str) -> str:
    item = _load_proposals().get(proposal_id)
    if item is None:
        return f"I have no change called '{proposal_id}'."
    rehearsal = item.get("rehearsal") or {}
    lines = [f"{item['id']}: {item['path']}  [{item['stage']}]",
             f"  reason: {item['reason']}",
             f"  size: {item['before']} -> {item['after']} characters",
             f"  confirmations: {', '.join(item['confirmations']) or 'none'} of "
             f"{CONFIRMATIONS}",
             f"  rehearsal: " + ("passed — " + rehearsal.get("command", "")
                                 if rehearsal.get("ok") else
                                 "not passed yet" if rehearsal else "not run")]
    return "\n".join(lines)


def diff(proposal_id: str, limit: int = 40) -> str:
    """A readable diff: the lines that are new, and the lines that go."""
    item = _load_proposals().get(proposal_id)
    if item is None:
        return f"I have no change called '{proposal_id}'."
    old_lines = item["old"].splitlines()
    new_lines = item["new"].splitlines()
    added = [line for line in new_lines if line not in old_lines][:limit]
    removed = [line for line in old_lines if line not in new_lines][:limit]
    lines = [f"{item['id']} {item['path']}"]
    lines += [f"  + {line}" for line in added]
    lines += [f"  - {line}" for line in removed]
    if not added and not removed:
        lines.append("  (only the order of lines changes)")
    return "\n".join(lines)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()
