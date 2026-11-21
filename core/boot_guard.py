"""core/boot_guard.py — a change Ultron made to its own code has to survive a start, or it is put back.

THE GAP THIS CLOSES
    `core/self_change.py` rehearses a change in a copy (the whole test harness), asks twice, and
    writes it. A `.py` change only runs when the program starts again, so the first real test of
    the written code is the next start, on the owner's machine, with nobody watching. A fault the
    tests could not see (a start-up path no test reaches, an import that only fails on Windows)
    left Ultron unable to open, and the only way back was a person with a terminal.

WHAT HAPPENS
    apply    `watch()` writes down the file, the digest of the old text and the digest of the new
             text in `config/self_change/boot-watch.json`. The kept copy of the old text is the
             one `apply` already makes.
    launch   `scripts/bootstrap.py` (run.bat and run.ps1 call it before `main.py`) runs
             `check_at_launch()`. A change that was never started is marked as started now. A
             change that was started on an earlier launch and never proved itself is put back.
    run      `arm()` starts a timer when the window is up. After HEALTHY_AFTER seconds, or when
             the window is closed normally, `mark_healthy()` takes the change off the list. If the
             thread that runs the assistant dies, `fail()` is called and the change is never
             trusted by this start, however long the window stays open.

    So a bad change costs one failed start, and the next start is the old code, with a sentence
    on the screen saying what was put back and why.

WHY THIS FILE IMPORTS NOTHING OF THE PROGRAM
    The failure it exists for is a program that cannot start. If it imported `core.failures` or
    `core.self_change` and a change had broken either, the guard would break with it. It uses the
    standard library only, `scripts/bootstrap.py` loads it by path, and both files are in
    `core/self_change.PROTECTED`: a change cannot remove its own safety net.

WHAT IT DOES NOT DO
    * It guards starts made with run.bat or run.ps1. `python main.py` skips `bootstrap.py`, so a
      change that stops that start from opening is not caught.
    * "Healthy" means the process stayed up for HEALTHY_AFTER seconds or ended normally, and the
      thread that runs the assistant did not die. A change that starts fine and misbehaves later is
      not this file's business; `revert` is for that.
    * It cannot tell the change from another cause: a start that failed for a missing package or a
      full disk is treated the same, and the message says so. A second launch made while the first is
      still inside its first HEALTHY_AFTER seconds is read as the first having failed.
    * It is not `native/ultron-core/src/watchdog/boot_guard.rs`, a design in the Rust crate that is not
      part of what runs. This file is what runs.
    * It never writes a file that is not exactly what `apply` wrote (digest checked), never one
      the referee list names, never through a link, and never from a change id that is not the
      shape `propose` makes. A tampered watch file cannot aim it at another file.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import stat
import tempfile
import threading
import time
from pathlib import Path

WATCH_NAME = "boot-watch.json"
HEALTHY_AFTER = 45.0          # seconds a start has to last before its change is trusted
MARKER = "restart-required.json"

# Copied from core/self_change.py on purpose (see "WHY THIS FILE IMPORTS NOTHING"). A test pins
# them equal, so they cannot drift apart without a failing build.
PROTECTED = (
    "core/policy.py",
    "core/confirm.py",
    "core/self_change.py",
    "core/boot_guard.py",
    "scripts/proof_gate.py",
    "scripts/bootstrap.py",
    "run.bat",
    "run.ps1",
    "config/api_keys.json",
)
NEVER_THROUGH = frozenset({".git", ".github", "__pycache__", ".venv", ".venv.old", "node_modules",
                           "build", "dist", ".pytest_cache", ".ruff_cache", ".mypy_cache",
                           ".hypothesis", ".arena", ".npm", "uploads"})

_ID = re.compile(r"^c[0-9a-f]{12}$")        # what `propose` makes; an id is never a path
_LOCK = threading.Lock()
_FAILED = threading.Event()      # set when the assistant's own thread died in this process
ROOT = Path(__file__).resolve().parent.parent


def _store(root, store) -> Path:
    return Path(store) if store else Path(root or ROOT) / "config" / "self_change"


def _digest(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _read(path: Path, keep_newlines: bool = False) -> str | None:
    """The text of a regular file, read the way `core/self_change` reads it; None for any other.

    `keep_newlines` returns it as it is on disk. The digests are of the text with `\\n` line ends, as
    `core/self_change` takes them; what is written back is the text as kept.
    """
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
            return None
        with path.open("r", encoding="utf-8", errors="replace",
                       newline="" if keep_newlines else None) as handle:
            return handle.read()
    except OSError:
        return None


def _write(path: Path, text: str) -> None:
    """Replace a file through a unique sibling, so a cut-off write never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = stat.S_IMODE(path.lstat().st_mode)
    except OSError:
        mode = 0o600
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        os.chmod(name, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    except BaseException:
        with contextlib.suppress(OSError):      # the error that matters is re-raised just below
            os.unlink(name)
        raise


def _load(store: Path) -> list[dict]:
    text = _read(store / WATCH_NAME)
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        return []
    rows = data.get("changes") if isinstance(data, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _save(store: Path, rows: list[dict]) -> None:
    path = store / WATCH_NAME
    if rows:
        _write(path, json.dumps({"changes": rows}, indent=1))
    else:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()


def _started(row: dict) -> int:
    try:
        return int(row.get("started") or 0)
    except (TypeError, ValueError):
        return 0


def watch(store, change: str, path: str, old_sha256: str, applied_sha256: str) -> None:
    """Called by `apply` before it writes: this change is on disk and has not yet been started."""
    store = Path(store)
    with _LOCK:
        rows = [row for row in _load(store) if row.get("change") != change]
        rows.append({"change": change, "path": path, "old_sha256": old_sha256,
                     "applied_sha256": applied_sha256, "started": 0,
                     "applied_at": time.strftime("%Y-%m-%d %H:%M:%S")})
        _save(store, rows)


def forget(store, change: str) -> None:
    """Called by `revert` and by a failed `apply`: this change is no longer on disk."""
    store = Path(store)
    with _LOCK:
        rows = _load(store)
        kept = [row for row in rows if row.get("change") != change]
        if len(kept) != len(rows):
            _save(store, kept)


def watching(store, change: str) -> bool:
    with _LOCK:
        return any(row.get("change") == change for row in _load(Path(store)))


def pending(store=None, root=None) -> list[dict]:
    """The changes that have not yet proved themselves, newest last."""
    with _LOCK:
        return _load(_store(root, store))


def _inside(root: Path, relative: str) -> Path | None:
    """The file a change may be put back to, or None. The same refusals as `self_change._inside`."""
    candidate = Path(relative)
    if not relative or candidate.is_absolute() or any(part in {".", ".."} for part in candidate.parts):
        return None
    base = root.resolve()
    target = base
    for part in candidate.parts:
        target = target / part
        if target.is_symlink() or getattr(target, "is_junction", lambda: False)():
            return None
    target = target.resolve()
    try:
        inside = target.relative_to(base)
    except ValueError:
        return None
    if inside.as_posix().casefold() in {name.casefold() for name in PROTECTED}:
        return None
    if any(part.casefold() in {name.casefold() for name in NEVER_THROUGH} for part in inside.parts):
        return None
    return target


def _put_back(root: Path, store: Path, row: dict) -> tuple[bool, str]:
    """Put one change back. (True, '') when the file is exactly what it was before `apply`."""
    change = str(row.get("change") or "")
    if not _ID.match(change):
        return False, "its id is not one this program made"
    target = _inside(root, str(row.get("path") or ""))
    if target is None:
        return False, "the file is not one that may be written from here"
    kept = _read(store / "backups" / f"{change}.bak")
    if kept is None or _digest(kept) != row.get("old_sha256"):
        return False, "the kept copy of the old file is missing, or is not what was recorded"
    current = _read(target)
    if current is None or _digest(current) != row.get("applied_sha256"):
        return False, "the file is not what the change wrote (it changed since), so it was left alone"
    exact = _read(store / "backups" / f"{change}.bak", keep_newlines=True)
    if exact is None:
        return False, "the kept copy of the old file could not be read again"
    try:
        _write(target, exact)
    except OSError as error:
        return False, f"the file could not be written: {error}"
    return True, ""


def _record(store: Path, row: dict, done: bool, why: str) -> str:
    """Say in the ledger and in the proposals what happened. Returns a sentence only on failure."""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    reason = ("the start that ran it did not stay up for "
              f"{int(HEALTHY_AFTER)} seconds" if done else f"could not be put back: {why}")
    try:
        ledger = store / "ledger.jsonl"
        entry = {"id": row.get("change"), "event": "reverted" if done else "revert-failed",
                 "path": row.get("path"), "at": now, "by": "boot guard", "reason": reason}
        previous = _read(ledger)
        if previous is None and os.path.lexists(ledger):
            raise OSError("the ledger is a link or not a regular file, and was left as it is")
        _write(ledger, (previous or "") + json.dumps(entry) + "\n")
        proposals = json.loads(_read(store / "proposals.json") or "{}")
        item = proposals.get(row.get("change")) if isinstance(proposals, dict) else None
        if done and isinstance(item, dict):
            item.update(stage="reverted", reverted_at=now, reverted_by="boot guard")
            _write(store / "proposals.json", json.dumps(proposals, indent=1))
    except (OSError, ValueError) as error:
        return f"The ledger could not be updated: {error}"
    return ""


def _clear_marker(root: Path, changes: list[str]) -> None:
    """`apply` leaves a note that a restart is needed. Once the change is gone it is not true."""
    marker = root / MARKER
    try:
        data = json.loads(_read(marker) or "{}")
    except ValueError:
        return
    if isinstance(data, dict) and data.get("change") in changes:
        with contextlib.suppress(OSError):
            marker.unlink()


def _words(outcome: dict) -> str:
    lines = ["", "Ultron changed its own code, and the start that ran the new code did not stay up for "
                  f"{int(HEALTHY_AFTER)} seconds or end normally. This cannot tell the change from "
                  "another cause (a missing package, a full disk). The change has been taken back:"]
    lines += [f"  put back: {item['path']} (change {item['change']})"
              + (" - never started: made after the one that failed, and put back too because it may "
                 "build on it" if item["never_started"] else "")
              for item in outcome["put_back"]]
    lines += [f"  NOT put back: {item['path']} (change {item['change']}) - {item['why']}"
              for item in outcome["left"]]
    if outcome["left"]:
        lines.append("A person has to look at what was left: the kept copies of the old files are in "
                     "config/self_change/backups.")
    lines += outcome["notes"]
    lines.append("")
    return "\n".join(lines)


def _undo_all(root: Path, store: Path, rows: list[dict], outcome: dict) -> None:
    for row in reversed(rows):                  # newest first, so a file changed twice unwinds in order
        done, why = _put_back(root, store, row)
        item = {"change": row.get("change"), "path": row.get("path"), "why": why,
                "never_started": _started(row) < 1}
        outcome["put_back" if done else "left"].append(item)
        note = _record(store, row, done, why)
        if note:
            outcome["notes"].append(note)
    _clear_marker(root, [str(item["change"]) for item in outcome["put_back"]])


def check_at_launch(root=None, store=None, say=None) -> dict:
    """The first thing a start does. Never raises: a guard that stops the launch is worse than none.

    Returns {"started": [ids now on their first start], "put_back": [...], "left": [...],
    "notes": [...]}, and says anything worth saying through `say(text)`.
    """
    outcome = {"started": [], "put_back": [], "left": [], "notes": []}
    say = say or (lambda _text: None)
    root = Path(root or ROOT)
    store = _store(root, store)
    try:
        with _LOCK:
            rows = _load(store)
            if any(_started(row) >= 1 for row in rows):
                _undo_all(root, store, rows, outcome)
                _save(store, [])
                say(_words(outcome))
            elif rows:
                for row in rows:
                    row["started"] = 1
                outcome["started"] = [str(row.get("change")) for row in rows]
                _save(store, rows)
                say(f"Ultron is starting code it changed itself ({', '.join(outcome['started'])}). "
                    f"If this start does not stay up for {int(HEALTHY_AFTER)} seconds, the next one "
                    "puts the old file back.")
    except Exception as error:                  # noqa: BLE001 - see the docstring: never stop a launch
        outcome["notes"].append(f"The boot guard could not finish: {error}")
        say(outcome["notes"][-1])
    return outcome


def fail() -> None:
    """The thread that runs the assistant died. This start no longer vouches for any change."""
    _FAILED.set()


def mark_healthy(root=None, store=None) -> int:
    """This start lasted: the changes that were started with it are trusted. Returns how many.

    Zero, and nothing changes, if `fail()` was called: a window that is still open over an assistant
    that is not running has not lasted.
    """
    if _FAILED.is_set():
        return 0
    store = _store(root, store)
    try:
        with _LOCK:
            rows = _load(store)
            kept = [row for row in rows if _started(row) < 1]    # applied during this run: not yet run
            if len(kept) != len(rows):
                _save(store, kept)
            return len(rows) - len(kept)
    except OSError:
        return 0


def arm(root=None, store=None, after: float = HEALTHY_AFTER) -> bool:
    """Start the timer that proves this start healthy. True when there is something to prove."""
    store = _store(root, store)
    if not any(_started(row) >= 1 for row in pending(store)):
        return False
    timer = threading.Timer(float(after), mark_healthy, kwargs={"root": root, "store": store})
    timer.daemon = True                         # a timer must never keep the program from closing
    timer.name = "boot-guard-timer"
    timer.start()
    return True
