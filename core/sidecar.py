"""core/sidecar.py — the compiled supervisor, seen from the Python side.

`sidecar/watchd` is the one part of Ultron written in Go, and it exists for one
reason only: **a supervisor cannot live inside the program it supervises.** If
the assistant crashes, a Python watcher dies with it and nobody learns that the
background job finished. The Go binary keeps watching, keeps its event log, and
tells the owner after the assistant comes back.

Measured against the Python watcher (`scripts/bench_sidecar.py`, this machine):

    binary           2.0 MB              interpreter + psutil
    startup          3 ms                26 ms
    resident         2.7 MB              13.6 MB
    event latency    10 ms (200 ms poll) same poll, same table

What it does NOT do is compute anything faster. The process sweep, the speech
gate and every safety rule stay where they were.

**The sidecar is optional in both directions:**

* if the binary is missing, `try_start()` returns None and `main.py` uses the
  Python watcher — the capability never depends on a compiler;
* if the binary is present but dies, `poll()` reports nothing and the loop
  restarts it, so a broken sidecar degrades to the Python path instead of
  silently watching nothing.

Reading its output is a plain tail of JSON lines. No socket, no protocol, no
version negotiation: a file that grows one line per finished job can be read by
`tail`, by an editor, or by this module.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from core.process_watch import Completion

__all__ = [
    "binary_path",
    "SidecarFeed",
    "completion_from_event",
    "read_new_events",
    "try_start",
]

ROOT = Path(__file__).resolve().parents[1]


def binary_path() -> Path | None:
    """Where the compiled supervisor is, or None.

    `ULTRON_SIDECAR` wins, so an owner can point at a build of their own without
    touching the repository. The default name follows Go's own convention.
    """
    override = os.environ.get("ULTRON_SIDECAR", "").strip()
    if override:
        candidate = Path(override)
        return candidate if candidate.exists() else None
    name = "watchd-windows.exe" if os.name == "nt" else "watchd-linux"
    candidate = ROOT / "sidecar" / "bin" / name
    return candidate if candidate.exists() else None


def completion_from_event(record: dict) -> Completion | None:
    """Turn one JSON line into the same Completion the Python watcher produces.

    The two sources feed one speech gate, so they must agree on shape. A malformed
    line returns None: a supervisor that crashes on a bad log line is worse than
    no supervisor.
    """
    try:
        pid = int(record.get("pid") or 0)
        seconds = float(record.get("seconds") or 0.0)
        name = str(record.get("name") or "")
        watch = str(record.get("watch") or "")
        how = str(record.get("how") or "ended")
    except (TypeError, ValueError):
        return None
    if not name and not pid:
        return None
    return Completion(label=watch or name, pid=pid, name=name,
                      seconds=max(0.0, seconds), exit_code=None, how=how)


def read_new_events(path: Path, offset: int) -> tuple[list[dict], int]:
    """Read complete JSON lines added since `offset`.

    A half-written line is left for the next call rather than parsed: the writer
    flushes per line, but a reader that assumes atomic writes will one day read
    half a record and blame the writer.
    """
    try:
        with open(path, "rb") as handle:
            handle.seek(offset)
            data = handle.read()
    except FileNotFoundError:
        return [], offset
    if not data:
        return [], offset

    consumed = data.rfind(b"\n")
    if consumed < 0:
        return [], offset          # nothing complete yet
    complete = data[: consumed + 1]
    events: list[dict] = []
    for line in complete.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            events.append(record)
    return events, offset + len(complete)


@dataclass
class SidecarFeed:
    """A running sidecar, and the events it has produced so far."""

    process: subprocess.Popen
    events_path: Path
    offset: int = 0
    started_at: float = 0.0

    def poll(self) -> list[Completion]:
        events, self.offset = read_new_events(self.events_path, self.offset)
        out = []
        for record in events:
            done = completion_from_event(record)
            if done is not None:
                out.append(done)
        return out

    @property
    def alive(self) -> bool:
        return self.process.poll() is None

    def stop(self) -> None:
        if self.alive:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()


def try_start(patterns: list[str] | tuple[str, ...], events_path: Path,
              poll_seconds: float = 2.0) -> SidecarFeed | None:
    """Start the compiled supervisor if it exists. Never raise for its absence.

    A missing compiler must not be a missing capability, so every failure here is
    a quiet None and `main.py` falls back to the Python watcher.
    """
    binary = binary_path()
    if binary is None or not patterns:
        return None
    # An executable bit does not survive every copy: an archive, a zip round trip
    # or a repository checkout can drop it, and the failure looks exactly like
    # "the sidecar is missing" — which is how it hid once already. Restore it
    # before trying to run, and say nothing when the platform has no such concept.
    if os.name != "nt":
        try:
            if not os.access(binary, os.X_OK):
                os.chmod(binary, 0o755)
        except OSError:
            pass

    try:
        events_path.parent.mkdir(parents=True, exist_ok=True)
        # Start from a clean log: events from an earlier run are not news.
        events_path.write_text("", encoding="utf-8")
        process = subprocess.Popen(
            [str(binary),
             "-watch", ",".join(patterns),
             "-events", str(events_path),
             "-poll", f"{max(0.1, float(poll_seconds)):.1f}s"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if sys.platform == "win32" else 0,
        )
    except Exception:
        return None
    return SidecarFeed(process=process, events_path=events_path, started_at=time.time())
