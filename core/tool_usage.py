"""Which tools are actually called — the other half of a trigger.

A condition in the instruction is a hope. The owner asked the right question about it:

    "they need a condition to get triggered, otherwise ULTRON will never use them"

A tool can be declared, described, permitted and still never be chosen. Nothing in
this project could tell the difference between "the user never needed it" and "the
model never once thought of it", because nothing counted the calls.

This module counts them. One line in the call path, one small object in the settings
file, and afterwards the question has an answer:

    usage.unused(all_tool_names)   -> the tools that have never been called
    usage.render(all_tool_names)   -> that answer in words, for tools_status

WHAT IT DELIBERATELY IS NOT
    Not analytics, not a profile, and not networked. It holds a count and a date per
    tool name, on this machine, in the settings file the owner can open and delete.
    Nothing here records what was asked, only which hand was used.

WHERE THE WRITE HAPPENS
    Saving a setting is a locked, flushed disk write that waits and retries (for up to
    0.3 s) when another thread or an antivirus scanner has the file. `note` is called from
    `_execute_tool_approved`, which runs on the event loop that also carries the voice,
    so a note made there used to stop everything for as long as that write took.
    Now: called on a thread that is running an event loop, `note` only puts the name in a
    queue and returns, and one background thread does the write. Called anywhere else
    (a worker thread, a script, the proof gate) it writes before it returns, exactly as
    before. `unused` and `render` wait for the queue to empty first (once, and for at most a
    second), so an answer about what has been called includes the call that is being made right
    now. `tools_status` is answered on the event loop, so that one tool can still wait for its
    own write; it is the only one. `read` does not wait; it is the plain file read the writer
    itself uses.
    What this costs: if the process is killed outright (not closed) within a few
    milliseconds of a call, that one count can be lost. A normal exit waits up to two
    seconds for the queue, and never longer, so a stuck disk cannot keep the app open.
"""

from __future__ import annotations

import asyncio
import atexit
import queue
import threading
import time

from core import failures
from memory import config_manager as settings

KEY = "tool_usage"
MAX_TOOLS = 200            # far more than the tool count; a bound, not a target

# Tool calls run on worker threads and several can finish together. `note` is a
# read-then-save, so without this two of them read the same counts and the second
# save dropped the first one's increment. (The settings file itself is safe from
# concurrent writers; this keeps the COUNT right.)
_NOTE_LOCK = threading.Lock()


def _iso(now: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(now))


def _on_an_event_loop() -> bool:
    """True when the calling thread is the one running an asyncio loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _record(name: str, when: float) -> None:
    """Add one call to the saved counts. Never raises (see `note`)."""
    try:
        with _NOTE_LOCK:
            counts = read()
            row = counts.get(name) if isinstance(counts.get(name), dict) else {}
            counts[name] = {"count": int(row.get("count", 0)) + 1,
                            "last": _iso(when)}
            if len(counts) > MAX_TOOLS:
                keep = sorted(counts.items(), key=lambda item: item[1].get("last", ""),
                              reverse=True)[:MAX_TOOLS]
                counts = dict(keep)
            settings.save_tool_usage(counts)
    except Exception as error:                                  # noqa: BLE001
        failures.note("tool_usage.note", error)


class _Writer:
    """One background thread that saves the calls noted on an event loop, in order."""

    def __init__(self) -> None:
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._waiting = 0                   # calls queued or being saved, not yet done

    def _ensure(self) -> threading.Thread:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                # A daemon: a disk that never answers must not keep the program from closing.
                self._thread = threading.Thread(target=self._run, name="tool-usage-writer",
                                                daemon=True)
                self._thread.start()
            return self._thread

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if isinstance(item, threading.Event):
                item.set()                  # everything queued before it has been saved
                continue
            try:
                _record(*item)
            finally:
                with self._lock:
                    self._waiting -= 1

    def enqueue(self, name: str, when: float) -> bool:
        """Queue one call for the writer. False when there is no writer to take it."""
        try:
            self._ensure()
        except RuntimeError as error:                           # no thread could be started
            failures.note("tool_usage.writer", error)
            return False
        with self._lock:
            self._waiting += 1
        self._queue.put_nowait((name, when))      # an unbounded queue: this never waits
        return True

    def settle(self, timeout: float) -> bool:
        with self._lock:
            if self._waiting == 0:
                return True                 # the usual case: nothing to wait for, no hop
            if threading.current_thread() is self._thread:
                return True                 # this IS the writer; waiting for itself would hang
        reached = threading.Event()
        self._queue.put_nowait(reached)
        self._ensure()
        return reached.wait(timeout)


_WRITER = _Writer()


def settle(timeout: float = 1.0) -> bool:
    """Wait up to `timeout` seconds until every call noted so far has been saved.

    True when they have. It returns at once when nothing is waiting, which is the usual case.
    """
    return _WRITER.settle(max(0.0, float(timeout)))


# A normal exit saves what is still queued. Bounded, and the writer is a daemon besides.
atexit.register(settle, 2.0)


def note(name: str) -> None:
    """Record one call of one tool. Never raises: a statistic is not worth a turn.

    A tool that fails after this point still counts as used, because the question
    being answered is "did the model reach for it", not "did it succeed". Failures
    have their own trail (`core/failures.py`).

    On an event loop this returns at once and the write happens on the writer thread;
    anywhere else it writes first. See "WHERE THE WRITE HAPPENS" above.
    """
    try:
        name = str(name or "").strip()
        if not name:
            return
        when = time.time()
        if _on_an_event_loop() and _WRITER.enqueue(name, when):
            return
        _record(name, when)             # not on a loop, or no writer could be started
    except Exception as error:                                  # noqa: BLE001
        failures.note("tool_usage.note", error)


def read() -> dict:
    """Every tool that has been called, with its count and the last time.

    This is the file as it is. A call noted on an event loop a moment ago may not be in it
    yet; `settle()` first if that matters (`unused` and `render` do).
    """
    try:
        value = settings.get_tool_usage()
    except Exception as error:                                  # noqa: BLE001
        failures.note("tool_usage.read", error)
        return {}
    return value if isinstance(value, dict) else {}


def unused(names) -> list[str]:
    """The tools that have never been called since this was first recorded."""
    settle()
    used = read()
    return sorted(str(name) for name in names if str(name) not in used)


def render(names) -> str:
    """One short answer about what has and has not been reached for.

    Said in words rather than a table because it is read out loud, and because the
    useful sentence is the last one: these tools exist and nothing has called them.
    """
    names = [str(name) for name in names]
    if not names:
        return "I have no tools to report on."
    settle()
    used = read()
    called = [name for name in names if name in used]
    never = sorted(name for name in names if name not in used)      # not `unused()`: that would wait again
    if not used:
        return (f"No tool has been called yet in this install, out of {len(names)}. "
                f"That is what a fresh install looks like — or the sign of a trigger "
                f"that never fires.")
    lines = [f"{len(called)} of {len(names)} tools have been called."]
    busiest = sorted(((name, row.get("count", 0), row.get("last", ""))
                      for name, row in used.items() if name in names),
                     key=lambda row: -row[1])[:5]
    if busiest:
        lines.append("Most used: " + ", ".join(f"{name} ({count})"
                                               for name, count, _last in busiest) + ".")
    if never:
        lines.append(f"Never called ({len(never)}): " + ", ".join(never[:15])
                     + (" …" if len(never) > 15 else "")
                     + ". A tool in this list has a description the model has not "
                       "found a reason to use.")
    else:
        lines.append("Every tool has been called at least once.")
    return " ".join(lines)
