"""
core/heartbeat.py — Client-side heartbeat emitter for ULTRON.
Emits periodic pings to the ultron-core supervisor over Named Pipe IPC (channel 0x06).

What this does and does not do, checked against `native/ultron-core/src/ipc/server.rs`:
the supervisor echoes each frame back. It does not yet act on a missing heartbeat
(`HEARTBEAT_TIMEOUT` is declared in `watchdog/boot_guard.rs` and used nowhere), so a
silent emitter costs nothing today. Nothing in the app starts this emitter yet.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from core import failures
from core.ipc_client import UltronIPCClient

DEFAULT_INTERVAL_S = 5.0


class HeartbeatEmitter:
    """Sends periodic heartbeat pings to the Rust supervisor."""

    def __init__(self, client: Optional[UltronIPCClient] = None,
                 interval: float = DEFAULT_INTERVAL_S):
        self.client = client or UltronIPCClient()
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._seq = 0
        self.delivered = 0      # frames the pipe accepted
        self._in_outage = False
        self._last_error = ""

    async def start(self) -> bool:
        """Connect and start the background loop.

        Returns False, and starts nothing, when the supervisor cannot be reached
        (`UltronIPCClient.connect` records why in `core.failures`). It used to
        start a loop either way, so "started" meant nothing.
        """
        if self._task is not None and not self._task.done():
            return True
        if not self.client.is_connected and not await self.client.connect():
            return False
        self._running = True
        self._task = asyncio.create_task(self._loop())
        return True

    async def stop(self) -> None:
        """Stop emitting heartbeats."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            # gather() hands the loop's own cancellation back as a value, so the
            # expected end is not an error, while a cancel aimed at the CALLER of
            # stop() still propagates (a bare `except CancelledError` ate it).
            (outcome,) = await asyncio.gather(self._task, return_exceptions=True)
            if isinstance(outcome, Exception):
                failures.note("heartbeat.stop", outcome)

    async def _beat(self) -> bool:
        """One heartbeat. True when the pipe took it. Reconnects once if it dropped."""
        try:
            if not self.client.is_connected and not await self.client.connect(retries=1):
                self._last_error = "not connected, and a reconnect failed"
                return False
            sent = await self.client.send_heartbeat(self._seq)
        except Exception as error:
            self._last_error = f"{type(error).__name__}: {error}"
            return False
        if not sent:
            self._last_error = "the pipe is not connected"
            return False
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        self.delivered += 1
        return True

    async def _loop(self) -> None:
        while self._running:
            ok = await self._beat()
            # Note the START of an outage and its END, never every tick: the failure
            # trail keeps 200 entries and a dead pipe at 5 s would fill it in 17 min.
            if not ok and not self._in_outage:
                self._in_outage = True
                failures.note("heartbeat.lost", self._last_error,
                              detail=f"{self.delivered} delivered before this")
            elif ok and self._in_outage:
                self._in_outage = False
                failures.note("heartbeat.restored",
                              "the supervisor is taking heartbeats again")
            await asyncio.sleep(self.interval)
