"""core/native_core.py — the Rust helper (`native/ultron-core`), seen from the Python side: the freeze watch.

What it is for. Ultron can freeze: the window stops answering, or the assistant's own loop stops. A program that
froze cannot tell anyone, so a second program is started beside it. Ultron sends that program a small message
every five seconds (`core/heartbeat.py`). When the messages stop for 30 seconds, the helper writes one line in
its log, and one more when they come back. That is all it does. It restarts nothing and ends nothing.

What counts as "Ultron answers". A message is sent only while the window ALSO answers (`window_gate`): the
window's one-second timer (`ui.py`, `_tick_clock`) stamps the time, and a stamp older than
`WINDOW_GRACE_SECONDS` holds the message back. So the messages stop when the window thread hangs, when the
assistant's loop hangs, and when the whole program hangs. The line in the log cannot say WHICH of them it was;
the failure trail in `core/failures.py` says it when the window was the one (`heartbeat.lost`).

It is switched off until the owner switches it on (`memory/config_manager.py`, `native_watch_enabled`), because
it starts a second program. The program is not in the repository: it is built by CI (`native-build.yml`, the
`ultron-core-windows-x64` download) or by `cargo build --release`. Without it, `begin` says so and nothing
else happens. `docs/FREEZE_WATCH.md` is the guide for the owner.

Following `core/sidecar.py`: a missing program is a None and not an error, a failure to start is noted in
`core.failures`, and the program's own output is in `logs/child-ultron-core.log`, never thrown away.
"""

from __future__ import annotations

import asyncio
import atexit
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from core import crash, failures
from core.heartbeat import HeartbeatEmitter
from memory import config_manager

__all__ = [
    "RELATIVE_PATH", "STALL_SECONDS", "WAIT_SECONDS", "WINDOW_GRACE_SECONDS", "FreezeWatch", "NativeCore",
    "arguments", "begin", "binary_path", "log_path", "previous_run", "report_for", "start", "why_missing",
    "window_gate",
]

ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = sys.platform == "win32"

#: Where `cargo build --release` (and `native-build.yml`) puts the program, from the repository root.
RELATIVE_PATH = Path("native/ultron-core/target/release/ultron-core.exe")
#: The limit the helper uses, which is `HEARTBEAT_TIMEOUT` in `native/ultron-core/src/watchdog/boot_guard.rs`.
STALL_SECONDS = 30
#: How long a helper that nobody connects to waits before it ends, which is `Options::default` in `ipc/server.rs`.
WAIT_SECONDS = 120
#: A window that has not run its one-second timer for longer than this is not answering. Shorter than the
#: stall limit, so a real hang is on the record before the limit ends; longer than any hiccup.
WINDOW_GRACE_SECONDS = 10.0

LOG_NAME = "ultron-core"
_ENVIRONMENT = "ULTRON_NATIVE_CORE"
_HEADER = "ultron-core started ---"     # the line `crash.child_log` writes at each start


def _chosen_path() -> Path:
    override = os.environ.get(_ENVIRONMENT, "").strip()
    return Path(override) if override else ROOT / RELATIVE_PATH


def binary_path() -> Optional[Path]:
    """Where the helper program is, or None.

    `ULTRON_NATIVE_CORE` wins, so the owner can point at a build of their own. It is Windows only, like the
    crate (`tokio::net::windows::named_pipe`). A path that was named and is wrong is None: it is not
    quietly replaced by another copy.
    """
    if not IS_WINDOWS:
        return None
    candidate = _chosen_path()
    return candidate if candidate.is_file() else None


def why_missing() -> str:
    """One sentence for the owner: why there is no helper to start, and what to do about it."""
    if not IS_WINDOWS:
        return "the freeze watch needs Windows: the helper program is built for Windows only, so nothing will watch here."
    return (f"the helper program is not at {_chosen_path()}. Download 'ultron-core-windows-x64' from the latest "
            "'native build' run on GitHub (Actions), or run 'cargo build --release' in native/ultron-core, and "
            "put it there; nothing will watch until it is there.")


def log_path() -> Path:
    """`logs/child-ultron-core.log`: everything the helper says, including its STALL and RECOVERED lines."""
    return crash.child_log_path(LOG_NAME)


def arguments(stall_seconds: float = STALL_SECONDS, wait_seconds: float = WAIT_SECONDS) -> list[str]:
    """The helper's command line, which is `Options::from_arguments` in `native/ultron-core/src/ipc/server.rs`.

    `--once` ends the helper with its one session, so it cannot outlive Ultron. `--wait-seconds` ends it
    when Ultron never connects. `--stall-seconds` is the limit.
    """
    return ["--once", f"--wait-seconds={wait_seconds:g}", f"--stall-seconds={stall_seconds:g}"]


@dataclass
class NativeCore:
    """The running helper."""

    process: subprocess.Popen
    started_at: float = 0.0

    @property
    def alive(self) -> bool:
        return self.process.poll() is None

    def stop(self) -> None:
        """End the helper: ask, wait five seconds, then insist. Safe to call twice and after it has ended."""
        try:
            if self.process.poll() is not None:
                return
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        except Exception as error:   # noqa: BLE001 — stopping runs at exit and must not raise there
            failures.note("native_core.stop", error)


def start(stall_seconds: float = STALL_SECONDS, wait_seconds: float = WAIT_SECONDS) -> Optional[NativeCore]:
    """Start the helper if it is there. Never raises: every failure is a None and a note in `core.failures`."""
    binary = binary_path()
    if binary is None:
        return None
    output = crash.child_log(LOG_NAME)
    try:
        process = subprocess.Popen(
            [str(binary), *arguments(stall_seconds, wait_seconds)],
            # What the helper says goes to `logs/child-ultron-core.log`. `crash.child_log` records why it
            # could not open that file, so the DEVNULL below always has a reason on record.
            stdout=output if output is not None else subprocess.DEVNULL,
            stderr=subprocess.STDOUT if output is not None else subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0,
        )
    except Exception as error:   # noqa: BLE001 — a helper that will not start is a note, never a crash
        failures.note("native_core.start", error, detail=str(binary))
        return None
    finally:
        if output is not None:
            output.close()          # the child keeps its own copy of the handle
    return NativeCore(process=process, started_at=time.monotonic())


# ── what the helper noted last time ─────────────────────────────────────────────────────────────────────

_RECOVERED_AFTER = re.compile(r"back after (\d+) s of silence")


def previous_run(path: Optional[Path] = None) -> dict:
    """What the helper wrote in the run BEFORE this one: how many freezes, the longest that ended, and
    whether the last one was still going when the log stopped.

    Read before `start()` adds the next header, so "after the last header" is the previous run. A missing
    log, or one with no freeze in it, is an empty dict.
    """
    path = path or log_path()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return {}
    except OSError as error:
        failures.note("native_core.previous_run", error, detail=str(path))
        return {}
    section = text.rsplit(_HEADER, 1)[-1]
    stalls = section.count("[Watch] STALL")
    if not stalls:
        return {}
    lengths = [int(found) for found in _RECOVERED_AFTER.findall(section)]
    return {
        "stalls": stalls,
        "longest": max(lengths, default=0),
        "unfinished": section.rfind("[Watch] STALL") > section.rfind("[Watch] RECOVERED"),
    }


def report_for(run: dict) -> Optional[str]:
    """The one line Ultron says at start when the last run had a freeze. None when it had none."""
    stalls = run.get("stalls", 0)
    if not stalls:
        return None
    parts = [f"last time, Ultron stopped answering {stalls} time{'s' if stalls != 1 else ''}"]
    if run.get("longest"):
        parts.append(f"the longest one that ended lasted {run['longest']} s")
    if run.get("unfinished"):
        parts.append("the last one had not ended when Ultron closed")
    return "SYS: Freeze watch: " + "; ".join(parts) + f". Details: logs/{log_path().name}"


# ── the start, as `main.py` uses it ────────────────────────────────────────────────────────────────────

def window_gate(window_silence: Callable[[], float]) -> Callable[[], Optional[str]]:
    """The check the emitter asks before each beat: None while the window answers, a sentence when it does not."""
    def gate() -> Optional[str]:
        silent = window_silence()
        if silent > WINDOW_GRACE_SECONDS:
            return f"the window has not answered for {silent:.0f} s"
        return None
    return gate


@dataclass
class FreezeWatch:
    """What `begin` hands back. It keeps the emitter alive: a task nobody refers to can be collected."""

    helper: NativeCore
    emitter: HeartbeatEmitter

    async def stop(self) -> None:
        await self.emitter.stop()
        self.helper.stop()


async def begin(say: Callable[[str], None], window_silence: Callable[[], float]) -> Optional[FreezeWatch]:
    """Start the freeze watch if the owner switched it on. Says what happened. Never raises.

    `say` writes a line in the activity log (thread-safe: `ui.write_log`). `window_silence` is the number of
    seconds since the window last answered (`JarvisUI.window_silence`).
    """
    try:
        if not config_manager.get_native_watch_enabled():
            return None
        if binary_path() is None:
            say(f"SYS: Freeze watch is on, but {why_missing()}")
            return None
        earlier = report_for(previous_run())
        if earlier:
            say(earlier)
        helper = await asyncio.to_thread(start)
        if helper is None:
            say(f"ERR: Freeze watch: the helper program would not start. See logs/{log_path().name} "
                "and the failure trail.")
            return None
        emitter = HeartbeatEmitter(gate=window_gate(window_silence))
        if not await emitter.start():
            helper.stop()
            say("ERR: Freeze watch: Ultron could not connect to the helper, so the helper was ended. "
                "The reason is in the failure trail.")
            return None
        atexit.register(helper.stop)
        say("SYS: Freeze watch is on. A helper program is noting when Ultron stops answering "
            f"(logs/{log_path().name}). It restarts nothing.")
        return FreezeWatch(helper=helper, emitter=emitter)
    except Exception as error:   # noqa: BLE001 — a failed extra must never take the assistant down with it
        failures.note("native_core.begin", error)
        say(f"ERR: Freeze watch could not start: {error}")
        return None
