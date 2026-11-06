"""core/process_watch.py — supervising the jobs Ultron did not start.

The owner asked for three things, in this order:

1. **Be aware of what is running in the background.** Not its own tasks — other
   programs: an agent in another window, a render, a build, a long download.
2. **Know when one finishes**, and say so: "the Antigravity agent replied".
3. **Never interrupt.** If the owner is talking to Ultron, the sentence waits.
   It is delivered when the talking stops, and several completions are merged
   into one sentence rather than fired one at a time.

## The rule that makes this safe to leave running

**This module observes. It never acts.** It calls no method that can change
another program: no `terminate`, no `kill`, no `suspend`, no signal, no priority
change. A supervisor that can kill is a supervisor that will one day kill the
wrong thing while the owner is in a meeting. `tests/test_process_watch.py` reads
this file and fails if any of those words appear as a call, so the rule survives
future edits.

Reading is not free of consequence either, so the read is cheap: one pass over
the process table per poll, only the processes already being watched are kept,
and the default poll is two seconds — about 0.02 ms of work per process.

## What "finished" means, and what it does not

A process that this module did not start has no exit code to read. Linux and
Windows both discard it when the parent reaps the child. So the honest report is
"ended", with the duration, and an exit code only when Ultron started the process
itself and therefore owns the handle (`adopt`). Saying "succeeded" without an
exit code would be a guess wearing a suit.

A process is identified by **pid plus create time**, never by pid alone. Pids are
reused, and a watcher that trusts a bare pid eventually reports that a job
finished because an unrelated program inherited its number.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

__all__ = [
    "Proc",
    "Completion",
    "Watcher",
    "SpeechGate",
    "Supervisor",
    "format_duration",
    "WATCHED_BY_DEFAULT",
]


# Programs worth watching out of the box. Patterns are matched against the
# process name, lower case, anywhere in the name: "Antigravity" catches
# "antigravity", "Antigravity Helper", and so on. Nothing is watched that the
# owner did not ask for: this list is a default, and `set_patterns` replaces it.
# One name, deliberately. Every extra pattern is a sentence the owner will hear
# about a program nobody asked about: "python" alone would announce every script
# on the machine, including Ultron's own tools. Add patterns with the ULTRON_WATCH
# environment variable, comma separated.
WATCHED_BY_DEFAULT: tuple[str, ...] = ("antigravity",)


def format_duration(seconds: float) -> str:
    """2 hr 13 min / 4 min 12 s / 0.8 s — as a person would say it."""
    seconds = max(0.0, float(seconds))
    if seconds < 1.0:
        return f"{seconds:.1f} s"
    if seconds < 60:
        return f"{seconds:.0f} s"
    minutes, rest = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes} min {rest} s" if rest else f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} hr {minutes} min" if minutes else f"{hours} hr"


@dataclass(frozen=True)
class Proc:
    """One process, as read. Frozen: an observation is not a control handle."""

    pid: int
    name: str
    create_time: float
    cmdline: tuple[str, ...] = ()

    @property
    def identity(self) -> tuple[int, float]:
        return (self.pid, self.create_time)

    def describe(self) -> str:
        return self.name or f"pid {self.pid}"


@dataclass(frozen=True)
class Completion:
    """A watched programme that has stopped."""

    label: str
    pid: int
    name: str
    seconds: float
    exit_code: int | None = None      # None = unknown, and it says so
    how: str = "ended"                # "ended" | "exited" (we own it)

    def sentence(self) -> str:
        """One sentence, in plain English, for a log line or for speech."""
        who = self.label or self.name or f"pid {self.pid}"
        took = format_duration(self.seconds)
        if self.exit_code is None:
            return f"{who} finished — it ran for {took}."
        if self.exit_code == 0:
            return f"{who} finished cleanly after {took}."
        return f"{who} stopped with code {self.exit_code} after {took}."


@dataclass
class _Watch:
    label: str
    patterns: tuple[str, ...] = ()
    pid: int | None = None
    seen: dict[tuple[int, float], Proc] = field(default_factory=dict)
    owned: object | None = None       # a Popen, when we started it ourselves


class Watcher:
    """A read-only view of the process table, filtered to what is watched.

    `library` is `psutil` in production and anything with the same three methods
    in a test, so the interesting cases — a reused pid, a process that vanishes
    between two reads, a table that raises — are tested without spawning
    processes to be unlucky with.
    """

    MAX_CMD = 6            # arguments kept per process; the rest is noise
    MAX_SNAPSHOT = 400     # never hold an unbounded list of strangers

    def __init__(self, library=None, clock: Callable[[], float] = time.monotonic):
        self._lib = library if library is not None else _psutil()
        self._clock = clock
        self._watches: list[_Watch] = []

    # ---- registration -------------------------------------------------

    def watch(self, *patterns: str, label: str = "") -> None:
        """Watch processes whose name contains any of `patterns`.

        Patterns, not regular expressions: a name someone types into a settings
        file should not be able to become a slow expression by accident.
        """
        clean = tuple(p.strip().lower() for p in patterns if str(p).strip())
        if not clean:
            raise ValueError("watch() needs at least one pattern")
        self._watches.append(_Watch(label=label or clean[0], patterns=clean))

    def watch_pid(self, pid: int, label: str = "") -> None:
        self._watches.append(_Watch(label=label or f"pid {pid}", pid=int(pid)))

    def adopt(self, process, label: str = "") -> None:
        """Take responsibility for reporting a process Ultron started itself.

        Owning the handle is the only way to report an exit code truthfully, so
        this is offered only for processes this program spawned.
        """
        pid = int(getattr(process, "pid", 0) or 0)
        if not pid:
            raise ValueError("adopt() needs a started process with a pid")
        self._watches.append(_Watch(label=label or f"pid {pid}", pid=pid, owned=process))

    def set_patterns(self, patterns: Iterable[str], label: str = "") -> None:
        """Replace the pattern watches. Adopted and pid watches are kept."""
        self._watches = [w for w in self._watches if w.pid is not None]
        if patterns:
            self.watch(*patterns, label=label)

    def watched_labels(self) -> list[str]:
        return [w.label for w in self._watches]

    # ---- reading ------------------------------------------------------

    def _sweep(self) -> list | None:
        """One pass over the process table, or None if the table could not be read.

        The difference between "the table is empty" and "I could not read the
        table" is the difference between *it finished* and *I do not know*, and a
        supervisor that confuses the two announces that a build completed because
        a permission check failed. None means "do not conclude anything yet".

        A process can also exit between the listing and the read of its details.
        That is a race, not a fault; `_proc` returns None and the loop moves on.
        """
        try:
            return list(self._lib.process_iter([
                "pid", "name", "create_time", "cmdline", "status"]))
        except Exception:
            return None

    def _proc(self, item) -> Proc | None:
        try:
            info = item.info
        except Exception:
            return None
        pid = info.get("pid")
        if not pid or pid == 0:
            return None
        try:
            created = float(info.get("create_time") or 0.0)
        except Exception:
            return None
        name = str(info.get("name") or "")
        raw = info.get("cmdline") or ()
        cmdline = tuple(str(part) for part in list(raw)[:self.MAX_CMD])
        return Proc(pid=int(pid), name=name, create_time=created, cmdline=cmdline)

    def live(self) -> list[Proc]:
        """Every watched process that is running now. Read-only."""
        found, _known = self._observe()
        return found

    def _observe(self) -> tuple[list[Proc], bool]:
        table = self._sweep()
        if table is None:
            return [], False
        found: list[Proc] = []
        for item in table:
            proc = self._proc(item)
            if proc is None:
                continue
            if self._matches(proc):
                found.append(proc)
                if len(found) >= self.MAX_SNAPSHOT:
                    break
        return found, True

    def _matches(self, proc: Proc) -> bool:
        name = proc.name.lower()
        for watch in self._watches:
            if watch.pid is not None:
                if proc.pid == watch.pid:
                    return True
                continue
            if any(pattern in name for pattern in watch.patterns):
                return True
        return False

    # ---- the important part -------------------------------------------

    def poll(self) -> list[Completion]:
        """Note what is running, and return the watches that have stopped.

        Called on a timer. Returns an event at most once per watch: the watch is
        retired after it reports, so a completion cannot be announced twice.
        """
        live, known = self._observe()
        if not known:
            return []                 # the table could not be read: conclude nothing
        running: dict[tuple[int, float], Proc] = {}
        names: dict[int, Proc] = {}
        for proc in live:
            running[proc.identity] = proc
            names.setdefault(proc.pid, proc)

        done: list[Completion] = []
        still: list[_Watch] = []
        now = time.time()          # wall clock: durations are compared with create_time

        def elapsed(proc: Proc | None) -> float:
            """How long it ran, or 0 when the start time cannot be trusted."""
            if proc is None:
                return 0.0
            started = proc.create_time
            if not started or started > now + 60:
                return 0.0            # a placeholder, not a time
            return max(0.0, now - started)

        for watch in self._watches:
            # --- a process Ultron started itself: the handle knows its code ---
            if watch.owned is not None:
                code = None
                try:
                    code = watch.owned.poll()
                except Exception:
                    code = None
                if code is None:
                    still.append(watch)
                    continue
                proc = _first(watch.seen) or _find(running, watch.pid)
                started = proc.create_time if proc else now
                done.append(Completion(
                    label=watch.label, pid=proc.pid if proc else 0,
                    name=proc.name if proc else watch.label,
                    seconds=elapsed(proc), exit_code=int(code), how="exited"))
                continue                      # retired: reported once

            # --- one specific pid. A new process wearing it is a finish. ---
            if watch.pid is not None:
                current = names.get(watch.pid)
                known = set(watch.seen)
                if current is not None and (not known or current.identity in known):
                    watch.seen[current.identity] = current
                    still.append(watch)
                    continue
                if known:
                    proc = _first(watch.seen)
                    done.append(Completion(
                        label=watch.label, pid=proc.pid, name=proc.name,
                        seconds=elapsed(proc), how="ended"))
                    continue                  # retired
                still.append(watch)           # not launched yet: wait quietly
                continue

            # --- a name pattern. A process ending while a new one starts is
            #     reported for the one that ended, and the watch survives. ---
            matched = [proc for proc in running.values()
                       if any(pattern in proc.name.lower() for pattern in watch.patterns)]
            vanished = [proc for identity, proc in watch.seen.items()
                        if identity not in running]
            if vanished:
                proc = vanished[0]
                watch.seen = {other.identity: other for other in matched}
                done.append(Completion(
                    label=watch.label, pid=proc.pid, name=proc.name,
                    seconds=elapsed(proc), how="ended"))
                still.append(watch)
                continue
            for proc in matched:
                watch.seen.setdefault(proc.identity, proc)
            still.append(watch)

        self._watches = still
        return done

    def _belongs(self, watch: _Watch, proc: Proc) -> bool:
        if watch.pid is not None:
            return proc.pid == watch.pid
        name = proc.name.lower()
        return any(pattern in name for pattern in watch.patterns)


def _first(mapping: dict) -> Proc | None:
    for value in mapping.values():
        return value
    return None


def _find(mapping: dict, pid: int) -> Proc | None:
    for proc in mapping.values():
        if proc.pid == pid:
            return proc
    return None


class SpeechGate:
    """Hold sentences while the owner is talking; release them when quiet.

    The rule, in the owner's words: *"if I'm speaking with Ultron, then it should
    tell me when I stop talking."* Speaking over a person is the rudest thing a
    voice assistant does, and it is the default behaviour of every one of them.

    Quiet means a continuous stretch with nothing happening — no speech from
    Ultron, no voice from the owner — of `quiet_for` seconds. A single poll with
    `busy=False` is not enough, because a person pauses to breathe.
    """

    def __init__(self, quiet_for: float = 1.4,
                 clock: Callable[[], float] = time.monotonic):
        self.quiet_for = float(quiet_for)
        self._clock = clock
        self._held: list[str] = []
        self._quiet_since: float | None = None

    # ---- the queue ----------------------------------------------------

    def hold(self, text: str) -> None:
        if text and text.strip():
            self._held.append(text.strip())
            if self._quiet_since is None:
                self._quiet_since = self._clock()

    @property
    def pending(self) -> int:
        return len(self._held)

    def ready(self, busy: bool) -> list[str]:
        """The sentences to say now — usually none.

        Returns one merged sentence when the queue has waited long enough, and
        empties the queue. Several completions in one quiet window are one
        announcement, not five: a list of five sentences is a status report, and
        nobody asked for a status report.
        """
        if busy:
            self._quiet_since = None
            return []
        now = self._clock()
        if self._quiet_since is None:
            self._quiet_since = now
        if not self._held:
            return []
        if now - self._quiet_since < self.quiet_for:
            return []
        batch = merge(self._held)
        self._held.clear()
        self._quiet_since = None
        return batch


def merge(lines: Sequence[str]) -> list[str]:
    """Fold several sentences into as few as read naturally."""
    lines = [line.strip() for line in lines if line and line.strip()]
    if len(lines) <= 1:
        return lines
    head, rest = lines[0], lines[1:]
    joined = ", ".join(sentence.rstrip(".") for sentence in rest)
    return [f"{head} {len(rest)} more: {joined}."]


class Supervisor:
    """Watch, record immediately, speak only when the room is quiet.

    Two channels, on purpose:

    * **the log** gets the line the moment the job ends, because a record that
      waits for silence is a record with gaps;
    * **the voice** waits for the owner to stop talking, because a sentence that
      lands mid-sentence is a sentence that has to be repeated.
    """

    def __init__(self, watcher: Watcher | None, gate: SpeechGate | None = None,
                 say: Callable[[str], None] | None = None,
                 log: Callable[[str], None] | None = None,
                 feed=None):
        """`watcher` and `feed` are both optional, and both are real.

        The in-process watcher is the default. The feed is the compiled sidecar,
        used when it exists because it keeps watching while the assistant is down.
        A supervisor with neither is legal and does nothing, which is exactly what
        should happen on a machine where neither source is available.
        """
        self.watcher = watcher
        self.feed = feed
        self.gate = gate or SpeechGate()
        self._say = say or (lambda text: None)
        self._log = log or (lambda text: None)
        self.completions: list[Completion] = []

    def tick(self, busy: bool = False) -> list[str]:
        """One turn of the crank. Returns what was said, for tests and logs."""
        finished: list[Completion] = []
        if self.watcher is not None:
            finished.extend(self.watcher.poll())
        if self.feed is not None:
            finished.extend(self.feed.poll())
            if not getattr(self.feed, "alive", True):
                # It stopped. Say so once, then let the caller fall back rather
                # than let a dead supervisor look like a quiet machine.
                self._log("The compiled watcher stopped; the in-process one takes over.")
                self.feed = None

        for done in finished:
            self.completions.append(done)
            self._log(done.sentence())
            self.gate.hold(done.sentence())

        said = self.gate.ready(busy)
        for line in said:
            self._say(line)
        return said

    def status_line(self) -> str:
        """What is running, in one line. For the agent to answer from."""
        if self.watcher is None:
            return "The in-process watcher is not the one running."
        running = self.watcher.live()
        if not running:
            return "Nothing I am watching is running."
        names = sorted({proc.describe() for proc in running})
        shown = ", ".join(names[:6])
        more = f", and {len(names) - 6} more" if len(names) > 6 else ""
        return f"{len(running)} watched process{'es' if len(running) != 1 else ''} running: {shown}{more}."


def _psutil():
    """Import psutil only when a watcher is actually constructed.

    `psutil` is in requirements, but the tests that read this file's text, and
    the tools that import the package's modules, must not need it to be present.
    """
    try:
        import psutil
        return psutil
    except ImportError as exc:      # pragma: no cover - a packaging fault
        raise RuntimeError(
            "process watching needs psutil: pip install psutil") from exc
