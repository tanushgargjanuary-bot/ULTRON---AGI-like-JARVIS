import asyncio
import os
import subprocess
import time
import unittest
from core.ipc_client import UltronIPCClient, PIPE_PATH
from core.audio_ring import AudioRingReader


class TestHybridIPCE2E(unittest.TestCase):
    def test_ipc_named_pipe_and_shared_memory(self):
        core_exe = os.path.join(
            os.path.dirname(__file__), "..", "native", "ultron-core", "target", "release", "ultron-core.exe"
        )
        if not os.path.exists(core_exe):
            self.skipTest("ultron-core.exe binary not found")

        proc = subprocess.Popen([core_exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
                connected = await client.connect(retries=5, delay=0.5)
                self.assertTrue(connected)
                self.assertTrue(client.is_connected)

                # Send heartbeat
                await client.send_heartbeat(seq=1)
                await asyncio.sleep(0.2)

                # Clean shutdown
                await client.close()
                self.assertFalse(client.is_connected)

            asyncio.run(run_client())
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
