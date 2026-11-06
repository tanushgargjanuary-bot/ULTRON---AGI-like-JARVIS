"""tests/test_connections.py — one connection, reused, and provably not leaked.

The performance document lists "no handshake per turn" as a lever worth 100-300 ms
on a real network. These tests prove the mechanism on loopback: a counting server
that reports how many connections the two call patterns open.

They also guard the two ways a connection pool breaks in the dark:

* a shared client closed by a caller that used `with` out of habit — the next
  request then fails in a different module, minutes later, with a message about a
  closed transport;
* an async client shared across two event loops, which works in a single test and
  fails the second time the app reconnects.
"""

from __future__ import annotations

import asyncio
import http.server
import socket
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from providers import connections


class _Counter(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.accepted = 0
        self.lock = threading.Lock()

    def get_request(self):
        request, address = super().get_request()
        try:
            request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        with self.lock:
            self.accepted += 1
        return request, address


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):                      # noqa: N802
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class PooledConnections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import httpx  # noqa: F401
        except Exception as exc:            # pragma: no cover
            raise unittest.SkipTest(f"httpx not installed: {exc}")
        cls.server = _Counter(("127.0.0.1", 0), _Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/probe"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        connections.close_all()

    def setUp(self):
        connections.reset_for_tests()
        self.server.accepted = 0

    def test_pooling_opens_one_connection_for_many_requests(self):
        client = connections.sync_client(timeout=10.0)
        for _ in range(5):
            client.get(self.url)
        self.assertEqual(self.server.accepted, 1,
                         "the pool opened a connection per request")

    def test_per_call_clients_open_one_each(self):
        import httpx
        for _ in range(5):
            with httpx.Client(timeout=10.0) as client:
                client.get(self.url)
        self.assertEqual(self.server.accepted, 5)

    def test_the_context_manager_does_not_close_the_shared_client(self):
        with connections.Pooled.sync(timeout=10.0) as first:
            first.get(self.url)
        self.assertFalse(first.is_closed, "leaving the block closed the pool")
        with connections.Pooled.sync(timeout=10.0) as second:
            second.get(self.url)
        self.assertIs(first, second, "the pool built a second client for the same options")
        self.assertEqual(self.server.accepted, 1)

    def test_different_options_never_share_a_client(self):
        fast = connections.sync_client(timeout=5.0)
        slow = connections.sync_client(timeout=20.0)
        self.assertIsNot(fast, slow, "a timeout change reused the wrong client")

    def test_stats_count_reuse(self):
        for _ in range(3):
            connections.sync_client(timeout=10.0).get(self.url)
        counts = connections.stats()
        self.assertEqual(counts["created"], 1)
        self.assertGreaterEqual(counts["reused"], 2)

    def test_close_all_closes_and_empties_the_pool(self):
        client = connections.sync_client(timeout=10.0)
        client.get(self.url)
        closed = connections.close_all()
        self.assertGreaterEqual(closed, 1)
        self.assertTrue(client.is_closed)
        self.assertEqual(connections.stats()["sync_open"], 0)

    def test_an_async_client_is_reused_within_one_loop(self):
        async def use_twice():
            first = connections.async_client(timeout=10.0)
            await first.get(self.url)
            second = connections.async_client(timeout=10.0)
            await second.get(self.url)
            return first is second

        self.assertTrue(asyncio.run(use_twice()))
        self.assertEqual(self.server.accepted, 1)

    def test_a_second_loop_gets_its_own_async_client(self):
        seen = []

        async def remember():
            client = connections.async_client(timeout=10.0)
            await client.get(self.url)
            seen.append(id(client))

        asyncio.run(remember())
        asyncio.run(remember())
        self.assertEqual(len(seen), 2)
        self.assertNotEqual(seen[0], seen[1],
                            "one async pool was shared across two loops")


class EveryCallSiteUsesThePool(unittest.TestCase):
    """Structural: the per-call client must not come back in a later edit."""

    EXPECTED = ("providers/llm_openai.py", "providers/stt_whisper.py",
                "providers/tts_elevenlabs.py", "providers/tts_piper.py")

    def test_no_provider_builds_a_client_per_call(self):
        offenders = []
        for relative in self.EXPECTED:
            text = (ROOT / relative).read_text(encoding="utf-8")
            for pattern in ("httpx.Client(", "httpx.AsyncClient(",
                            "_httpx.Client(", "_httpx.AsyncClient("):
                if pattern in text:
                    offenders.append(f"{relative}: {pattern}")
        self.assertEqual(offenders, [], f"a per-call client came back: {offenders}")

    def test_they_use_the_pool(self):
        for relative in self.EXPECTED:
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("connections.Pooled", text,
                          f"{relative} does not use the shared pool")


if __name__ == "__main__":
    unittest.main()
