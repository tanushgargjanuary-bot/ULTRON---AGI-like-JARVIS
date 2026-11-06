"""core/crash.py — a crash that leaves a record, instead of a window that vanishes.

Ultron runs with its console hidden. On Windows it is started with `pythonw`, so
`sys.stderr` is not a console at all, and an unhandled exception has nowhere to go.
Measured before this module existed: no crash handler anywhere in 93,000 lines, and
`core/failures.py` keeps its trail in memory, so a process that dies takes the trail
with it. The owner's experience of a crash was a window that disappeared.

Three registrations fix that, and each covers a different death:

    sys.excepthook            an exception that reaches the top of the main thread
    threading.excepthook      the same in a worker thread, where most of this app runs
    sys.unraisablehook        a failure inside __del__ or a dying generator
    faulthandler              a native fault — a Qt or audio DLL — which Python never
                              sees and which only faulthandler can report

The report is a small text file in `logs/`, capped at KEEP files, and it is written to
be read by a person: the time, the build, the kind, the message, the traceback, and the
last two hundred notes the assistant made before it fell. Secrets are removed from it,
because a report that captures an API key is worse than no report.

`history()` and `digest()` read those files back, so the next run knows what the last
one died of. That is the part that makes self-repair possible: a change to its own code
can start from what actually broke, rather than from a guess.
"""

from __future__ import annotations

import faulthandler
import platform
import re
import sys
import threading
import time
import traceback
from pathlib import Path

from core import failures

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "logs"
KEEP = 20                     # reports kept; the oldest goes first, well before any budget
PREFIX = "crash-"
FAULT = "faulthandler.log"
FAULT_MAX = 256 * 1024        # a native fault log is appended to until it is cut

# Anything that looks like a credential is replaced before a report is written. This
# list is about shape, not about any one provider: a report can hold the arguments of
# the call that died, and an argument can be a key.
_SECRETS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{10,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)([\"']?\s*[:=]\s*[\"']?)([^\s\"',}]{6,})"),
)

_state = {"installed": False, "root": ROOT, "fault_file": None}
_lock = threading.Lock()


def _folder(root: Path | None = None) -> Path:
    return (Path(root) if root else _state["root"]) / "logs"


def _say(line: str) -> None:
    """Write to the console if there is one. Under `pythonw` there is not."""
    stream = getattr(sys, "stderr", None)
    if stream is None:
        return
    try:
        stream.write(line.rstrip("\n") + "\n")
        stream.flush()
    except (OSError, ValueError):
        return


def redact(text: str) -> str:
    """Remove anything shaped like a credential from text that is about to be saved."""
    cleaned = str(text)
    for pattern in _SECRETS:
        if pattern.groups >= 3:
            cleaned = pattern.sub(lambda match: match.group(1) + match.group(2)
                                  + "<removed>", cleaned)
        else:
            cleaned = pattern.sub("<removed>", cleaned)
    return cleaned


def build() -> str:
    """The build number this process is running, for the first line of a report."""
    try:
        return (ROOT / "packaging" / "version.txt").read_text(encoding="utf-8").strip()
    except OSError as error:
        failures.note("crash.build", error)
        return "unknown"


def _tail_trail() -> str:
    """The notes the assistant made before it fell, oldest first."""
    notes = failures.recent(limit=60)
    if not notes:
        return "  (no note was left before the crash)"
    lines = []
    for note in notes:
        where = note.get("where", "?")
        lines.append(f"  {where}: {note.get('kind', '')}: {str(note.get('error', ''))[:160]}")
    return "\n".join(lines)


def compose(error: BaseException | str, *, where: str = "uncaught", thread: str = "") -> str:
    """The text of a report. Pure, so a test can check it without writing a file."""
    if isinstance(error, BaseException):
        kind = type(error).__name__
        message = str(error)
        trace = "".join(traceback.format_exception(type(error), error,
                                                   error.__traceback__))
    else:
        kind, message, trace = "Reported", str(error), ""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"time: {stamp}",
        f"build: {build()}",
        f"kind: {kind}",
        f"where: {where}{(' in ' + thread) if thread else ''}",
        f"message: {message}",
        f"platform: {platform.platform()}",
        f"python: {platform.python_version()}",
        "",
        "traceback:",
        trace.rstrip() or "  (none — this was reported, not raised)",
        "",
        "what it was doing just before:",
        _tail_trail(),
        "",
        "written by core/crash.py. Read it, then delete it if it holds anything private.",
    ]
    return redact("\n".join(lines)) + "\n"


def report(error: BaseException | str, *, where: str = "uncaught",
           thread: str = "", root: Path | None = None) -> str:
    """Write one report and return its path. Never raises — see the note below.

    A crash handler that throws replaces a crash with a crash. Every step here is
    guarded, and the guard records its own failure rather than passing silently; the
    only thing this function promises is that it returns a string.
    """
    folder = _folder(root)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = _free_name(folder)
        path.write_text(compose(error, where=where, thread=thread), encoding="utf-8")
        _rotate(folder)
        return str(path)
    except OSError as error_io:
        failures.note("crash.report", error_io, detail="a crash could not be written down")
        return ""


def _free_name(folder: Path) -> Path:
    """A name nothing else holds.

    The stamp is to the second, and two crashes can share a second — one in the main
    thread and one in a worker is ordinary. Without this the second would overwrite
    the first, which is the one failure mode a crash log cannot have.
    """
    stem = f"{PREFIX}{time.strftime('%Y%m%d-%H%M%S')}"
    path = folder / f"{stem}.txt"
    count = 2
    while path.exists():
        path = folder / f"{stem}-{count}.txt"
        count += 1
    return path


def _rotate(folder: Path) -> None:
    """Keep the newest KEEP reports. An assistant running for a year stays small."""
    try:
        reports = sorted(folder.glob(f"{PREFIX}*.txt"))
        for old in reports[:-KEEP] if len(reports) > KEEP else ():
            old.unlink()
    except OSError as error:
        failures.note("crash.rotate", error)


# The stamp in a report's name, and the copy number that a shared second adds.
_NAME = re.compile(r"(\d{8}-\d{6})(?:-(\d+))?$")


def _order(path: Path) -> tuple:
    """Newest first: by stamp, then by copy number, then by write time.

    Sorting by file name is not enough. Two crashes can share a second, and the copy
    gets a "-2" suffix: a dash sorts before a dot, so the newer report would come out
    first in a list that is read as "the newest is at the top".
    """
    match = _NAME.search(path.stem)
    stamp = match.group(1) if match else path.stem
    copy = int(match.group(2) or 0) if match else 0
    try:
        written = path.stat().st_mtime
    except OSError:
        written = 0.0
    return (stamp, copy, written)


def paths(root: Path | None = None) -> list[Path]:
    """Every report on this machine, newest first."""
    try:
        return sorted(_folder(root).glob(f"{PREFIX}*.txt"), key=_order, reverse=True)
    except OSError as error:
        failures.note("crash.paths", error)
        return []


def _header(path: Path) -> dict:
    """The key: value lines at the top of a report, without reading the traceback."""
    header: dict = {}
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    break
                key, _, value = line.partition(":")
                header[key.strip()] = value.strip()
    except (OSError, ValueError) as error:
        failures.note("crash.header", error, detail=str(path))
    header["path"] = str(path)
    header.setdefault("time", "")
    return header


def history(limit: int = 10, root: Path | None = None) -> list[dict]:
    """The last `limit` crashes, newest first, as records with a path to the full text."""
    return [_header(path) for path in paths(root)][:max(1, int(limit))]


def read(path: str | Path) -> str:
    """One report in full, for a person or for the model to quote."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        failures.note("crash.read", error, detail=str(path))
        return ""


def digest(limit: int = 3, root: Path | None = None) -> str:
    """A few sentences about what has crashed, for the model to work from.

    Written to be spoken: the kind, the place and the time, newest first, then a count.
    """
    rows = history(limit=limit, root=root)
    total = len(paths(root))
    if not rows:
        return "I have no record of crashing on this machine."
    lines = [f"I have {total} crash report(s) on this machine. The newest:"]
    for row in rows:
        lines.append(f"  {row.get('time', '?')} — {row.get('kind', '?')} at "
                     f"{row.get('where', '?')}: {row.get('message', '')[:140]}")
    lines.append(f"The full text of the newest is {rows[0]['path']}. Read it before "
                 f"changing code, and fix the cause rather than the symptom.")
    return "\n".join(lines)


def last_trace(limit: int = 40, root: Path | None = None) -> str:
    """The traceback of the newest report, cut to a few lines.

    A crash report is evidence; this is the part that names the fault.
    """
    rows = history(limit=1, root=root)
    if not rows:
        return ""
    text = read(rows[0]["path"])
    lines = text.splitlines()
    try:
        start = lines.index("traceback:")
    except ValueError:
        return text[-2000:]
    return "\n".join(lines[start:start + limit])


def startup_notice(root: Path | None = None) -> str:
    """One line for the activity log when the last run died, or an empty string.

    Said in the log rather than as a question: the owner is starting their assistant,
    not opening a bug tracker. The offer to look is the next sentence they choose.
    """
    rows = history(limit=1, root=root)
    if not rows:
        return ""
    row = rows[0]
    return (f"SYS: I crashed on {row.get('time', '?')} — {row.get('kind', '?')} at "
            f"{row.get('where', '?')}. Say \"why did you crash\" to see it.")


def clear(root: Path | None = None) -> int:
    """Delete every report. Returns how many. Used by tests and by the owner."""
    removed = 0
    for path in paths(root):
        try:
            path.unlink()
            removed += 1
        except OSError as error:
            failures.note("crash.clear", error, detail=str(path))
    return removed


def _on_exception(kind, value, tb) -> None:
    """The main-thread hook: Python's own, plus a file."""
    path = report(value, where="main thread")
    _say(f"[Ultron] it crashed: {kind.__name__ if isinstance(kind, type) else kind}: "
         f"{value}")
    if path:
        _say(f"[Ultron] the report is in {path}")
    return path


def _on_thread(args) -> None:
    """A worker thread died. This app runs most of its long work in those."""
    report(args.exc_value, where="worker thread",
           thread=getattr(args.thread, "name", "") if args.thread else "")


def _on_unraisable(args) -> None:
    """A failure inside __del__ or a dying generator: nothing above can catch it."""
    report(args.exc_value or args.exc_type, where="unraisable",
           thread=str(getattr(args, "object", ""))[:60])


def install(root: Path | None = None) -> dict:
    """Register every handler. Safe to call twice; the second call changes nothing.

    Returns what was installed, so the caller and the proof gate can check it rather
    than assume it.
    """
    with _lock:
        if _state["installed"]:
            return {"installed": True, "again": True, "root": str(_state["root"])}
        if root is not None:
            _state["root"] = Path(root)
        folder = _folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            failures.note("crash.install", error, detail="no folder for reports")
        sys.excepthook = _on_exception
        if hasattr(threading, "excepthook"):
            threading.excepthook = _on_thread
        if hasattr(sys, "unraisablehook"):
            sys.unraisablehook = _on_unraisable
        _arm_faulthandler(folder)
        _state["installed"] = True
        return {"installed": True, "again": False, "root": str(_state["root"]),
                "folder": str(folder), "keep": KEEP}


def _arm_faulthandler(folder: Path) -> None:
    """A native fault has no Python traceback; this is the only record of one."""
    path = folder / FAULT
    try:
        if path.exists() and path.stat().st_size > FAULT_MAX:
            path.write_text("", encoding="utf-8")
        handle = path.open("a", encoding="utf-8")
        faulthandler.enable(file=handle)
        _state["fault_file"] = handle       # keep the handle alive for the process
    except (OSError, ValueError, RuntimeError) as error:
        failures.note("crash.faulthandler", error,
                      detail="native faults will not be recorded")


def is_installed() -> bool:
    """Whether the handlers are in place — read by the proof gate and the tests."""
    return bool(_state["installed"]) and sys.excepthook is _on_exception


def folder(root: Path | None = None) -> str:
    """Where reports go, so a person can be told without reading this file."""
    return str(_folder(root))


def summary(root: Path | None = None) -> dict:
    """How many reports, and what kind they were, for a status line."""
    rows = history(limit=KEEP, root=root)
    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row.get("kind", "?")] = kinds.get(row.get("kind", "?"), 0) + 1
    return {"reports": len(paths(root)), "kinds": kinds,
            "newest": rows[0]["time"] if rows else "",
            "folder": folder(root)}
