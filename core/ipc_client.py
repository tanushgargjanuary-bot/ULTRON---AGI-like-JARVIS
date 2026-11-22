"""Named pipe IPC client for communicating with ultron-core supervisor.

Wire format (see `schema/ultron_ipc.fbs` and `native/ultron-core/src/ipc/server.rs`):
a 6-byte header `<BBL` (magic, channel id, payload length) and then the payload.
The Rust server echoes every channel-0x06 frame back and ends the session on 0xFF.

This client is a Windows feature: only the Proactor event loop can open a named
pipe. On any other loop `connect()` returns False and says why in `core.failures`.
"""

import asyncio
import struct
from typing import Callable, Dict, List, Optional

from core import failures

MAGIC = 0xA1
HEADER_SIZE = 6
PIPE_PATH = r"\\.\pipe\ultron-core"
# The largest frame body either side will accept (`native/ultron-core/src/ipc/server.rs`
# has the same number). The length field is a u32, so a corrupt or hostile header can ask
# for 4 GiB; the Rust server allocates that up front, before it has read one byte of it.
MAX_PAYLOAD = 1 << 20

# Channel ids that both sides of the pipe agree on (`schema/ultron_ipc.fbs`).
CHANNEL_HEARTBEAT = 0x06
CHANNEL_SHUTDOWN = 0xFF


class UltronIPCClient:
    """AsyncIO Named Pipe client connecting Python agent to Rust ultron-core."""

    def __init__(self, pipe_path: str = PIPE_PATH):
        self.pipe_path = pipe_path
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._handlers: Dict[int, List[Callable[[bytes], None]]] = {}
        self._connected = False
        self._listen_task: Optional[asyncio.Task] = None
        self._connect_failure_noted = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _note_connect_failure(self, error, detail: str) -> None:
        """One note per outage. A caller that polls `connect()` every few seconds
        (the heartbeat emitter does) must not push everything else out of the
        200-entry failure trail."""
        if not self._connect_failure_noted:
            self._connect_failure_noted = True
            failures.note("ipc_client.connect", error, detail=detail)

    async def connect(self, retries: int = 5, delay: float = 1.0) -> bool:
        """Connect to the Rust Named Pipe server via Windows Proactor loop."""
        loop = asyncio.get_running_loop()
        if not hasattr(loop, "create_pipe_connection"):
            # Raising AttributeError here would crash whoever asked; "not connected"
            # is the honest answer and the caller already handles it.
            self._note_connect_failure(
                "this event loop cannot open a named pipe "
                "(only the Windows Proactor loop can)", self.pipe_path)
            return False
        last_error: Optional[BaseException] = None
        self._release_transport("ipc_client.connect.release")   # one from a lost session
        for attempt in range(retries):
            try:
                reader = asyncio.StreamReader()
                protocol = asyncio.StreamReaderProtocol(reader)
                transport, _ = await loop.create_pipe_connection(
                    lambda: protocol, self.pipe_path
                )
                writer = asyncio.StreamWriter(transport, protocol, reader, loop)
                self._reader = reader
                self._writer = writer
                self._connected = True
                self._connect_failure_noted = False
                self._listen_task = asyncio.create_task(self._listen_loop())
                return True
            except (FileNotFoundError, OSError) as error:
                last_error = error
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
        if last_error is not None:
            self._note_connect_failure(
                last_error, f"{self.pipe_path}: gave up after {retries} tries")
        return False

    def _release_transport(self, where: str) -> None:
        """Hand the pipe handle back now, not when the garbage collector gets to it.

        A session can end without `close()` ever running: the server hung up, a frame had
        the wrong magic or was over the limit. `close()` then skipped the writer because
        `_connected` was already False, and the next `connect()` replaced it, so every
        lost session left one transport open until a collection (a ResourceWarning in the
        tests, a held pipe handle on Windows).
        """
        writer = self._writer
        if writer is None:
            return
        try:
            writer.close()
        except Exception as error:
            failures.note(where, error, detail=self.pipe_path)

    async def _listen_loop(self):
        """Continuously decode wire frames from Rust."""
        try:
            await self._decode_frames()
        finally:
            self._connected = False
            self._release_transport("ipc_client.listen.close")

    async def _decode_frames(self):
        while self._connected and self._reader:
            try:
                header = await self._reader.readexactly(HEADER_SIZE)
                magic, channel_id, payload_len = struct.unpack("<BBL", header)
                if magic != MAGIC:
                    failures.note("ipc_client.listen",
                                  f"invalid magic 0x{magic:02X}; closing the session",
                                  detail=self.pipe_path)
                    break
                if payload_len > MAX_PAYLOAD:
                    failures.note("ipc_client.listen",
                                  f"frame of {payload_len} bytes is over the {MAX_PAYLOAD} "
                                  "limit; closing the session",
                                  detail=self.pipe_path)
                    break

                payload = await self._reader.readexactly(payload_len)
                for handler in self._handlers.get(channel_id, []):
                    try:
                        handler(payload)
                    except Exception as e:
                        failures.note(f"ipc_client.handler.0x{channel_id:02X}", e)
            except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
                break

    def on(self, channel_id: int):
        """Decorator to register a callback for a specific channel ID."""
        def decorator(fn: Callable[[bytes], None]):
            self._handlers.setdefault(channel_id, []).append(fn)
            return fn
        return decorator

    async def send(self, channel_id: int, payload: bytes) -> bool:
        """Send a formatted wire frame to Rust.

        Returns True when the frame was handed to the pipe and False when there is
        no connection or the payload is over `MAX_PAYLOAD`. It used to return nothing
        in both cases, so a caller could not tell a delivered frame from one that was
        dropped.
        """
        if not self._writer or not self._connected:
            return False
        if len(payload) > MAX_PAYLOAD:
            # The server ends the session on a frame this size; refusing here keeps the
            # session, and says why instead of letting the pipe close under the caller.
            failures.note("ipc_client.send",
                          f"payload of {len(payload)} bytes is over the {MAX_PAYLOAD} limit; "
                          "not sent", detail=self.pipe_path)
            return False
        header = struct.pack("<BBL", MAGIC, channel_id, len(payload))
        self._writer.write(header + payload)
        await self._writer.drain()
        return True

    async def send_heartbeat(self, seq: int = 0) -> bool:
        """Send a lightweight heartbeat payload (`Heartbeat` table: u64 ms, u32 seq)."""
        import time
        now_ms = int(time.time() * 1000)
        payload = struct.pack("<QI", now_ms, seq & 0xFFFFFFFF)
        return await self.send(CHANNEL_HEARTBEAT, payload)

    async def close(self):
        """Signal clean shutdown."""
        if self._connected:
            try:
                await self.send(CHANNEL_SHUTDOWN, b"")
            except Exception as error:
                failures.note("ipc_client.close.send", error,
                              detail="the pipe was already gone; closing anyway")
            self._connected = False
        # Also when the session had already ended on its own: the handle is still ours.
        writer, self._writer = self._writer, None
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as error:
                failures.note("ipc_client.close.writer", error)
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
