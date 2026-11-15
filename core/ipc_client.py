import asyncio
import struct
from typing import Callable, Dict, List, Optional

MAGIC = 0xA1
HEADER_SIZE = 6
PIPE_PATH = r"\\.\pipe\ultron-core"


class UltronIPCClient:
    """AsyncIO Named Pipe client connecting Python agent to Rust ultron-core."""

    def __init__(self, pipe_path: str = PIPE_PATH):
        self.pipe_path = pipe_path
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._handlers: Dict[int, List[Callable[[bytes], None]]] = {}
        self._connected = False
        self._listen_task: Optional[asyncio.Task] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self, retries: int = 5, delay: float = 1.0) -> bool:
        """Connect to the Rust Named Pipe server via Windows Proactor loop."""
        loop = asyncio.get_running_loop()
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
                self._listen_task = asyncio.create_task(self._listen_loop())
                return True
            except (FileNotFoundError, OSError):
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
        return False

    async def _listen_loop(self):
        """Continuously decode wire frames from Rust."""
        while self._connected and self._reader:
            try:
                header = await self._reader.readexactly(HEADER_SIZE)
                magic, channel_id, payload_len = struct.unpack("<BBL", header)
                if magic != MAGIC:
                    print(f"[IPC] Protocol error: invalid magic 0x{magic:02X}")
                    break

                payload = await self._reader.readexactly(payload_len)
                for handler in self._handlers.get(channel_id, []):
                    try:
                        handler(payload)
                    except Exception as e:
                        print(f"[IPC] Error in channel 0x{channel_id:02X} handler: {e}")
            except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
                break
        self._connected = False

    def on(self, channel_id: int):
        """Decorator to register a callback for a specific channel ID."""
        def decorator(fn: Callable[[bytes], None]):
            self._handlers.setdefault(channel_id, []).append(fn)
            return fn
        return decorator

    async def send(self, channel_id: int, payload: bytes):
        """Send a formatted wire frame to Rust."""
        if not self._writer or not self._connected:
            return
        header = struct.pack("<BBL", MAGIC, channel_id, len(payload))
        self._writer.write(header + payload)
        await self._writer.drain()

    async def send_heartbeat(self, seq: int = 0):
        """Send a lightweight heartbeat payload."""
        import time
        now_ms = int(time.time() * 1000)
        payload = struct.pack("<QI", now_ms, seq)
        await self.send(0x06, payload)

    async def close(self):
        """Signal clean shutdown."""
        if self._connected:
            try:
                await self.send(0xFF, b"")
            except Exception:
                pass
            self._connected = False
            if self._writer:
                try:
                    self._writer.close()
                    await self._writer.wait_closed()
                except Exception:
                    pass
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
