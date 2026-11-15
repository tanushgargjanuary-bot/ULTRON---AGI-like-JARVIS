"""
core/heartbeat.py — Client-side heartbeat emitter for ULTRON.
Emits periodic pings to the ultron-core supervisor over Named Pipe IPC (channel 0x06).
"""

from __future__ import annotations

import asyncio
import os
import struct
import time
from typing import Optional

from core.ipc_client import IPCClient, CHANNEL_HEARTBEAT

DEFAULT_INTERVAL_S = 5.0


class HeartbeatEmitter:
    """Sends periodic heartbeat pings to the Rust supervisor."""

    def __init__(self, client: Optional[IPCClient] = None, interval: float = DEFAULT_INTERVAL_S):
        self.client = client or IPCClient()
        self.interval = interval
        self.start_time = time.monotonic()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the heartbeat background loop."""
        if not self.client.is_connected:
            await self.client.connect()
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop emitting heartbeats."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        pid = os.getpid()
        while self._running:
            uptime = int(time.monotonic() - self.start_time)
            # 8 bytes: PID (uint32) + Uptime (uint32)
            payload = struct.pack("<II", pid, uptime)
            try:
                await self.client.send_frame(CHANNEL_HEARTBEAT, payload)
            except Exception as e:
                # Log without crashing the emitter
                pass
            await asyncio.sleep(self.interval)
