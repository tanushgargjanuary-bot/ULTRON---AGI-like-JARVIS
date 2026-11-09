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

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
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
_change_lock = threading.RLock()


def change_lock():
    """Serialize interactive and background self-change operations."""
    return _change_lock


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
    is_junction = getattr(folder, "is_junction", lambda: False)()
    if folder.is_symlink() or is_junction:
        raise OSError("The self-change store must not be a symlink or junction.")
    return folder


def _read_regular_text(path: Path) -> str:
    """Read a regular file only. Never follow a symlink from the state directory."""
    path = Path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return ""
    if (stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)
            or info.st_nlink > 1):
        raise OSError(f"Refusing a linked or non-regular self-change state file: {path.name}")
    return path.read_text(encoding="utf-8", errors="replace")


def _atomic_write_text(
    path: Path,
    text: str,
    default_mode: int = 0o600,
    expected_sha256: str | None = None,
) -> None:
    """Replace a file through a unique, exclusively-created sibling.

    A fixed temporary path can be pre-created as a link. Writing to that name
    would then write through the link before os.replace runs. mkstemp creates a
    unique file with exclusive creation, and replace swaps the directory entry
    rather than following a destination symlink or hard link.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    parent_is_junction = getattr(path.parent, "is_junction", lambda: False)()
    if path.parent.is_symlink() or parent_is_junction:
        raise OSError(f"Refusing a linked self-change directory: {path.parent.name}")

    mode = default_mode
    try:
        current = path.lstat()
    except FileNotFoundError:
        current = None
    if current is not None:
        if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
            raise OSError(f"Refusing to replace a non-regular self-change file: {path.name}")
        mode = stat.S_IMODE(current.st_mode)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        os.chmod(temporary_name, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            # fdopen owns the descriptor from this point. Do not close its old
            # integer again after the context exits; the OS may have reused it.
            descriptor = -1
            handle.write(str(text))
            handle.flush()
            os.fsync(handle.fileno())
        if expected_sha256 is not None:
            current_text = _read_regular_text(path)
            if _content_digest(current_text) != expected_sha256:
                raise ValueError(
                    f"{path.name} changed while the self-change operation was being prepared."
                )
        os.replace(temporary_name, path)
    except BaseException:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as cleanup_error:
                failures.note("self_change.temp_descriptor_close", cleanup_error)
        try:
            os.unlink(temporary_name)
        except OSError as cleanup_error:
            failures.note("self_change.temp_unlink", cleanup_error)
        raise


def _content_digest(text: str) -> str:
    """Stable digest used to reject stale apply and revert operations."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _proposals_file() -> Path:
    return store() / "proposals.json"


def _ledger_file() -> Path:
    return store() / "ledger.jsonl"


def _load_proposals() -> dict:
    try:
        data = json.loads(_read_regular_text(_proposals_file()))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_proposals(data: dict) -> None:
    _atomic_write_text(_proposals_file(), json.dumps(data, indent=1))


def _note(entry: dict) -> None:
    path = _ledger_file()
    with _change_lock:
        previous = _read_regular_text(path)
        _atomic_write_text(path, previous + json.dumps(entry) + "\n")


@implements("DBMS", 4, "Log-based recovery")
def ledger(limit: int = 20) -> list[dict]:
    """Every change this module made, newest first."""
    try:
        lines = _read_regular_text(_ledger_file()).splitlines()
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
    if not relative:
        return None
    relative_path = Path(relative)
    if relative_path.is_absolute() or any(part in {".", ".."} for part in relative_path.parts):
        return None
    base = root().resolve()
    candidate = base
    for part in relative_path.parts:
        candidate = candidate / part
        try:
            is_junction = getattr(candidate, "is_junction", lambda: False)()
            if candidate.is_symlink() or is_junction:
                return None
        except OSError:
            return None
    target = candidate.resolve()
    try:
        inside = target.relative_to(base)
    except ValueError:
        return None
    # Check the resolved target, not only the model-supplied path. Otherwise a
    # harmless-looking symlink can alias a protected referee file.
    protected = {name.replace("\\", "/").casefold() for name in PROTECTED}
    if inside.as_posix().casefold() in protected:
        return None
    if any(part.casefold() in {name.casefold() for name in SKIP_DIRS}
           for part in inside.parts):
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
    # Store the resolved project-relative target. Re-resolving the model-supplied
    # symlink name later could otherwise redirect an approved proposal to another file.
    canonical_path = target.relative_to(root().resolve()).as_posix()
    old = _read_regular_text(target)
    new = _apply_edit(old, find, replace, new_text)
    if len(new) > MAX_PATCH:
        raise ValueError(f"That change is {len(new)} characters; the limit is "
                         f"{MAX_PATCH}. Split it into smaller changes.")
    if new == old:
        raise ValueError("That change would leave the file exactly as it is.")
    proposal = {
        "id": "c" + uuid.uuid4().hex[:12],
        "path": canonical_path,
        "reason": reason,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stage": "proposed",
        "before": len(old),
        "after": len(new),
        "old_sha256": _content_digest(old),
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
    current = _read_regular_text(target)
    expected_old = proposal.get("old_sha256") or _content_digest(proposal.get("old", ""))
    if _content_digest(current) != expected_old:
        raise ValueError(
            f"{proposal['path']} changed after this proposal was created. "
            "Nothing was overwritten. Create and rehearse a new proposal."
        )
    backup = store() / "backups"
    backup.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(backup / f"{proposal_id}.bak", proposal["old"])
    _atomic_write_text(
        target, proposal["new"], default_mode=0o644, expected_sha256=expected_old
    )
    proposal["applied_sha256"] = _content_digest(proposal["new"])
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
    current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    expected_applied = proposal.get("applied_sha256") or _content_digest(proposal.get("new", ""))
    if _content_digest(current) != expected_applied:
        return (
            f"Cannot revert {proposal['path']}: it changed after {proposal_id} was applied. "
            "The current file was left untouched."
        )
    _atomic_write_text(
        target, _read_regular_text(kept), default_mode=0o644,
        expected_sha256=expected_applied,
    )
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
        _atomic_write_text(marker, json.dumps({
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "change": proposal["id"],
            "path": proposal["path"],
            "reason": proposal["reason"],
            "note": ("Ultron changed its own code. Restart to run it. The session is "
                     "kept: memory, ledger and workspace live in files."),
        }, indent=1))
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
