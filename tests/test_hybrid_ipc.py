"""Tests for the hybrid Rust/Python IPC layer: `core/ipc_client.py` and `core/heartbeat.py`.

The end-to-end test needs the Windows binary `ultron-core.exe` and skips without it.
`.github/workflows/native-build.yml` builds the binary on a Windows machine and runs that test against it; a skip
fails that job.
The other classes run everywhere: they speak the same 6-byte frame protocol over a
local TCP socket, with a stand-in for `native/ultron-core/src/ipc/server.rs`
(check the magic, echo channel 0x06, end the session on 0xFF), so the client's
framing, error reporting and the heartbeat emitter are exercised on every machine.
"""

import asyncio
import os
import struct
import subprocess
import tempfile
import time
import unittest

from core import failures
from core.audio_ring import AudioRingReader
from core.heartbeat import HeartbeatEmitter
from core.ipc_client import (
    CHANNEL_HEARTBEAT, CHANNEL_SHUTDOWN, HEADER_SIZE, MAGIC, MAX_PAYLOAD, PIPE_PATH,
    UltronIPCClient,
)


class TestHybridIPCE2E(unittest.TestCase):
    def test_ipc_named_pipe_and_shared_memory(self):
        core_exe = os.path.join(
            os.path.dirname(__file__), "..", "native", "ultron-core", "target", "release", "ultron-core.exe"
        )
        if not os.path.exists(core_exe):
            self.skipTest("ultron-core.exe binary not found")

        # The core's output goes to a file and is shown if the test fails: a binary that
        # cannot bind its pipe says so on its own output, and DEVNULL threw that away.
        output = tempfile.TemporaryFile()
        self.addCleanup(output.close)
        proc = subprocess.Popen([core_exe], stdout=output, stderr=subprocess.STDOUT)
        try:
            # Allow Rust core time to bind Named Pipe and shared memory
            time.sleep(1.0)

            # 1. Verify Shared Memory Ring
            reader = AudioRingReader()
            self.assertIsNotNone(reader.handle)
            self.assertIsNotNone(reader.view)
            frames = reader.read_latest_frames()
            self.assertIsInstance(frames, list)
            reader.close()

            # 2. Verify Named Pipe Client
            async def run_client():
                client = UltronIPCClient(PIPE_PATH)
                echoed = []
                client.on(CHANNEL_HEARTBEAT)(echoed.append)
                connected = await client.connect(retries=5, delay=0.5)
                self.assertTrue(connected)
                self.assertTrue(client.is_connected)

                # Send heartbeat; the server sends a channel-0x06 frame back unchanged
                self.assertTrue(await client.send_heartbeat(seq=1))
                for _ in range(30):
                    if echoed:
                        break
                    await asyncio.sleep(0.1)
                self.assertEqual(len(echoed), 1, "the server did not send the heartbeat back")
                self.assertEqual(len(echoed[0]), 12, "a heartbeat is a u64 time and a u32 sequence number")
                self.assertEqual(struct.unpack("<QI", echoed[0])[1], 1, "the sequence number came back changed")

                # Clean shutdown
                await client.close()
                self.assertFalse(client.is_connected)

            asyncio.run(run_client())
        except Exception as error:
            output.seek(0)
            said = output.read().decode("utf-8", errors="replace")[-2000:] or "(nothing)"
            raise AssertionError(f"{error!r}\n--- ultron-core said ---\n{said}") from error
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()


class FakeSupervisor:
    """What `native/ultron-core/src/ipc/server.rs::handle_client` does, over TCP."""

    def __init__(self):
        self.frames = []          # (channel_id, payload) in arrival order
        self.server = None
        self.port = 0

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()

    async def _handle(self, reader, writer):
        try:
            while True:
                header = await reader.readexactly(HEADER_SIZE)
                magic, channel, length = struct.unpack("<BBL", header)
                if magic != MAGIC:
                    break
                payload = await reader.readexactly(length)
                self.frames.append((channel, payload))
                if channel == CHANNEL_HEARTBEAT:
                    writer.write(header + payload)
                    await writer.drain()
                elif channel == CHANNEL_SHUTDOWN:
                    break
        except (asyncio.IncompleteReadError, ConnectionError) as error:
            self.ended_by = error      # the client hung up; that is how sessions end
        finally:
            writer.close()


async def attach(client, port):
    """Wire a client to the fake supervisor the way `connect()` wires it to a pipe."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    client._reader, client._writer, client._connected = reader, writer, True
    client._listen_task = asyncio.create_task(client._listen_loop())


async def wait_until(predicate, seconds=2.0):
    """Poll a condition on the running loop; True when it became true in time."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.005)
    return predicate()


class IpcClientFraming(unittest.TestCase):
    def setUp(self):
        failures.clear()

    def test_heartbeat_frame_matches_the_schema_and_is_echoed(self):
        async def scenario():
            supervisor = FakeSupervisor()
            await supervisor.start()
            client = UltronIPCClient()
            echoed = []
            client.on(CHANNEL_HEARTBEAT)(echoed.append)
            await attach(client, supervisor.port)
            self.assertTrue(await client.send_heartbeat(seq=7))
            self.assertTrue(await wait_until(lambda: echoed))
            await client.close()
            await wait_until(lambda: supervisor.frames
                             and supervisor.frames[-1][0] == CHANNEL_SHUTDOWN)
            await supervisor.stop()
            return supervisor.frames, echoed

        frames, echoed = asyncio.run(scenario())
        beats = [p for c, p in frames if c == CHANNEL_HEARTBEAT]
        self.assertEqual(len(beats), 1)
        timestamp_ms, seq = struct.unpack("<QI", beats[0])   # schema: u64 + u32
        self.assertEqual(seq, 7)
        self.assertLess(abs(timestamp_ms - time.time() * 1000), 60_000)
        self.assertEqual(echoed, beats, "the echo must reach the registered handler")
        self.assertEqual(frames[-1][0], CHANNEL_SHUTDOWN)

    def test_send_says_whether_the_frame_went_out(self):
        # It returned None either way, so a dropped frame looked like a sent one.
        client = UltronIPCClient()
        self.assertIs(asyncio.run(client.send(CHANNEL_HEARTBEAT, b"x")), False)
        self.assertIs(asyncio.run(client.send_heartbeat(1)), False)

    def test_a_handler_that_raises_is_noted_and_does_not_stop_the_loop(self):
        async def scenario():
            supervisor = FakeSupervisor()
            await supervisor.start()
            client = UltronIPCClient()
            good = []

            @client.on(CHANNEL_HEARTBEAT)
            def bad(_payload):
                raise ValueError("handler blew up")

            client.on(CHANNEL_HEARTBEAT)(good.append)
            await attach(client, supervisor.port)
            await client.send_heartbeat(1)
            await client.send_heartbeat(2)
            await wait_until(lambda: len(good) == 2)
            await client.close()
            await supervisor.stop()
            return good

        good = asyncio.run(scenario())
        self.assertEqual(len(good), 2, "the second handler and second frame still arrive")
        wheres = [n["where"] for n in failures.recent()]
        self.assertIn("ipc_client.handler.0x06", wheres)

    def test_bad_magic_is_noted_and_ends_the_session(self):
        async def scenario():
            async def rogue(reader, writer):
                try:
                    writer.write(struct.pack("<BBL", 0x00, 0x01, 0))
                    await writer.drain()
                    await asyncio.sleep(0.5)
                finally:
                    writer.close()      # also when the test ends first and cancels this

            server = await asyncio.start_server(rogue, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            client = UltronIPCClient()
            await attach(client, port)
            await wait_until(lambda: not client.is_connected)
            alive = client.is_connected
            await client.close()
            server.close()
            await server.wait_closed()
            return alive

        self.assertFalse(asyncio.run(scenario()))
        notes = [n for n in failures.recent() if n["where"] == "ipc_client.listen"]
        self.assertEqual(len(notes), 1)
        self.assertIn("invalid magic 0x00", notes[0]["error"])

    def test_a_frame_over_the_limit_is_noted_and_ends_the_session_unread(self):
        # A u32 length can claim 4 GiB. The client must not wait for (and buffer) it.
        async def scenario():
            async def rogue(reader, writer):
                try:
                    writer.write(struct.pack("<BBL", MAGIC, 0x01, 0xFFFFFFFF))
                    await writer.drain()
                    await asyncio.sleep(0.5)
                finally:
                    writer.close()

            server = await asyncio.start_server(rogue, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            client = UltronIPCClient()
            await attach(client, port)
            ended = await wait_until(lambda: not client.is_connected)
            await client.close()
            server.close()
            await server.wait_closed()
            return ended

        self.assertTrue(asyncio.run(scenario()), "the session must end, not wait for 4 GiB")
        notes = [n for n in failures.recent() if n["where"] == "ipc_client.listen"]
        self.assertEqual(len(notes), 1)
        self.assertIn("over the", notes[0]["error"])

    def test_a_payload_over_the_limit_is_refused_and_the_session_survives(self):
        async def scenario():
            supervisor = FakeSupervisor()
            await supervisor.start()
            client = UltronIPCClient()
            await attach(client, supervisor.port)
            refused = await client.send(0x01, b"x" * (MAX_PAYLOAD + 1))
            exact = await client.send(0x01, b"y" * MAX_PAYLOAD)
            await wait_until(lambda: len(supervisor.frames) == 1)
            alive = client.is_connected
            await client.close()
            await supervisor.stop()
            return refused, exact, alive, [len(p) for _c, p in supervisor.frames]

        refused, exact, alive, sizes = asyncio.run(scenario())
        self.assertIs(refused, False)
        self.assertIs(exact, True, "the limit itself is allowed")
        self.assertTrue(alive)
        self.assertEqual(sizes[:1], [MAX_PAYLOAD])
        notes = [n for n in failures.recent() if n["where"] == "ipc_client.send"]
        self.assertEqual(len(notes), 1)

    def test_a_session_that_ends_on_its_own_releases_the_pipe(self):
        # The server hanging up ends the listen loop with `_connected` False, and
        # close() used to skip the writer then: the transport stayed open.
        async def scenario():
            async def hangs_up(reader, writer):
                writer.close()

            server = await asyncio.start_server(hangs_up, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            client = UltronIPCClient()
            await attach(client, port)
            writer = client._writer
            ended = await wait_until(lambda: not client.is_connected)
            await asyncio.sleep(0.05)
            closing_after_the_session = writer.transport.is_closing()
            await client.close()
            server.close()
            await server.wait_closed()
            return ended, closing_after_the_session, client._writer

        ended, released, writer_after = asyncio.run(scenario())
        self.assertTrue(ended)
        self.assertTrue(released, "the transport is closed as soon as the session is over")
        self.assertIsNone(writer_after, "and close() lets go of it")

    def test_the_rust_server_has_the_same_cap(self):
        # Only the native build check builds and runs the Rust program, on Windows. This suite checks the
        # contract on the source: the two ends must agree, and the check must be before the allocation.
        import re
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "native" / "ultron-core" / "src"
                  / "ipc" / "server.rs").read_text(encoding="utf-8")
        found = re.search(r"MAX_PAYLOAD_LEN: usize = (1 << 20|1048576);", source)
        self.assertIsNotNone(found, "server.rs must define MAX_PAYLOAD_LEN = 1 MiB, like the client")
        self.assertLess(source.index("payload_len <= MAX_PAYLOAD_LEN"),
                        source.index("let mut payload = vec![0u8; payload_len]"),
                        "the length is checked before the buffer is allocated")

    def test_connect_without_a_named_pipe_loop_says_so_and_returns_false(self):
        async def scenario():
            if hasattr(asyncio.get_running_loop(), "create_pipe_connection"):
                return None
            client = UltronIPCClient("no-such-pipe")
            first = await client.connect(retries=1, delay=0)
            second = await client.connect(retries=1, delay=0)
            return first, second

        outcome = asyncio.run(scenario())
        if outcome is None:
            self.skipTest("this loop can open pipes; the Windows path is the e2e test")
        self.assertEqual(outcome, (False, False))
        notes = [n for n in failures.recent() if n["where"] == "ipc_client.connect"]
        self.assertEqual(len(notes), 1, "polling connect() must not repeat the note")
        self.assertIn("named pipe", notes[0]["error"])


class StubClient:
    """A client whose pipe we can break on purpose."""

    pipe_path = "stub"

    def __init__(self, connect_ok=True):
        self.connect_ok = connect_ok
        self.is_connected = False
        self.beats = []
        self.fail_with = None
        self.connect_calls = 0

    async def connect(self, retries=5, delay=1.0):
        self.connect_calls += 1
        self.is_connected = self.connect_ok
        return self.connect_ok

    async def send_heartbeat(self, seq=0):
        if self.fail_with is not None:
            raise self.fail_with
        if not self.is_connected:
            return False
        self.beats.append(seq)
        return True


class HeartbeatEmitterTests(unittest.TestCase):
    def setUp(self):
        failures.clear()

    def test_module_imports_and_uses_the_real_client_names(self):
        # core/heartbeat.py imported `IPCClient` and `CHANNEL_HEARTBEAT`, neither of
        # which existed, so the module could not be imported at all.
        emitter = HeartbeatEmitter()
        self.assertIsInstance(emitter.client, UltronIPCClient)
        self.assertEqual(CHANNEL_HEARTBEAT, 0x06)

    def test_start_reports_false_when_the_supervisor_is_unreachable(self):
        async def scenario():
            stub = StubClient(connect_ok=False)
            emitter = HeartbeatEmitter(stub, interval=0.01)
            started = await emitter.start()
            await emitter.stop()
            return started, emitter._task

        started, task = asyncio.run(scenario())
        self.assertIs(started, False)
        self.assertIsNone(task, "no loop may run for a connection that never existed")

    def test_sequence_numbers_count_up_and_stop_is_clean(self):
        async def scenario():
            stub = StubClient()
            emitter = HeartbeatEmitter(stub, interval=0.01)
            self.assertTrue(await emitter.start())
            await wait_until(lambda: len(stub.beats) >= 3)
            await emitter.stop()
            at_stop = len(stub.beats)
            await asyncio.sleep(0.05)
            return stub.beats, at_stop, len(stub.beats)

        beats, at_stop, later = asyncio.run(scenario())
        self.assertEqual(beats[:3], [0, 1, 2])
        self.assertEqual(at_stop, later, "nothing may be sent after stop()")
        self.assertEqual(failures.recent(), [], "a normal stop is not a failure")

    def test_an_outage_is_noted_once_and_recovery_is_noted(self):
        async def scenario():
            stub = StubClient()
            emitter = HeartbeatEmitter(stub, interval=0.005)
            await emitter.start()
            await wait_until(lambda: len(stub.beats) >= 2)
            stub.connect_ok = False               # supervisor went away
            stub.is_connected = False
            await wait_until(lambda: stub.connect_calls > 20)   # ~20 failed ticks
            stub.connect_ok = True                # supervisor came back
            await wait_until(lambda: any(n["where"] == "heartbeat.restored"
                                         for n in failures.recent()))
            await emitter.stop()
            return stub

        stub = asyncio.run(scenario())
        wheres = [n["where"] for n in failures.recent()]
        self.assertEqual(wheres.count("heartbeat.lost"), 1,
                         "20 failed ticks must make ONE note, not twenty")
        self.assertEqual(wheres.count("heartbeat.restored"), 1)
        self.assertGreater(stub.connect_calls, 20, "it must keep trying to reconnect")

    def test_an_exception_from_the_client_is_noted_not_swallowed(self):
        async def scenario():
            stub = StubClient()
            stub.fail_with = RuntimeError("pipe exploded")
            emitter = HeartbeatEmitter(stub, interval=0.005)
            await emitter.start()
            await wait_until(lambda: any(n["where"] == "heartbeat.lost"
                                         for n in failures.recent()))
            await emitter.stop()

        asyncio.run(scenario())
        lost = [n for n in failures.recent() if n["where"] == "heartbeat.lost"]
        self.assertEqual(len(lost), 1)
        self.assertIn("pipe exploded", lost[0]["error"])


if __name__ == "__main__":
    unittest.main()
