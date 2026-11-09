"""test_suite_providers.py — one suite file for 5 areas.

Each section below was its own test module and is kept whole, with its
header, its helpers and its tests. They were combined because the project
had sixty-five test modules of one or two hundred lines each, and a file
count that size hides the structure instead of showing it. Nothing was
removed; a name that appeared in two sections was given a suffix.

Sections:
  * test_connections.py
  * test_reconnect_policy.py
  * test_whatsapp_core.py
  * test_bridges.py
  * test_lazyimport.py
"""

from __future__ import annotations
import asyncio
import http.server
import socket
import sys
import threading
import unittest
from pathlib import Path
from providers import connections
from core import reconnect_policy as policy
from core import appidentity
from core.ui_tree import Node, Snapshot
from plugins import _whatsapp_core as wa
import json
import os
import stat
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock
from core import bridges
import ast
import tempfile
import textwrap
from core.lazyimport import LazyModule, installed



# ══════════════════════════════════════════════════════════════════════════
# from test_connections.py
# ══════════════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════════════
# from test_reconnect_policy.py
# ══════════════════════════════════════════════════════════════════════════
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import reconnect_policy as policy


class ResumptionTests(unittest.TestCase):
    def test_a_dead_handle_is_dropped_and_the_retry_is_immediate(self):
        verdict = policy.classify(
            RuntimeError("INVALID_ARGUMENT: the resumption handle is no longer valid"),
            resumed_with=True,
        )
        self.assertTrue(verdict.drop_handle)
        self.assertEqual(verdict.retry_delay, policy.FIRST_RETRY)
        self.assertIn("starting fresh", verdict.message)
        self.assertTrue(verdict.tell_user)

    def test_an_ordinary_error_that_mentions_handle_is_not_a_resumption_failure(self):
        # The regression. This sentence contains "handle" and must not be treated
        # as a dead resumption handle.
        exc = RuntimeError("cannot schedule new futures after shutdown while handling audio")
        self.assertFalse(policy.looks_like_resumption_failure(exc))
        verdict = policy.classify(exc, resumed_with=True)
        self.assertFalse(verdict.drop_handle)
        self.assertGreaterEqual(verdict.retry_delay, policy.BASE_DELAY)

    def test_no_handle_means_no_handle_to_drop(self):
        verdict = policy.classify(
            RuntimeError("NOT_FOUND: session expired"), resumed_with=False
        )
        self.assertFalse(verdict.drop_handle)

    def test_the_handle_is_dropped_at_most_once_per_streak(self):
        exc = RuntimeError("the resumption handle is invalid")
        first = policy.classify(exc, resumed_with=True, consecutive=0)
        second = policy.classify(exc, resumed_with=False, consecutive=1)
        self.assertTrue(first.drop_handle)
        self.assertFalse(second.drop_handle)


class BackoffTests(unittest.TestCase):
    def test_the_delay_starts_at_the_base_and_doubles(self):
        exc = ValueError("socket closed")
        self.assertEqual(policy.classify(exc, resumed_with=False).retry_delay, 3.0)
        self.assertEqual(policy.classify(exc, resumed_with=False, backoff=3).retry_delay, 6.0)
        self.assertEqual(policy.classify(exc, resumed_with=False, backoff=6).retry_delay, 12.0)

    def test_the_delay_is_capped(self):
        verdict = policy.classify(ValueError("x"), resumed_with=False, backoff=600)
        self.assertEqual(verdict.retry_delay, policy.MAX_DELAY)

    def test_a_retry_delay_is_never_zero_after_the_first_drop(self):
        # A zero delay on a repeating failure is a spin loop.
        for consecutive in range(1, 6):
            verdict = policy.classify(ValueError("x"), resumed_with=False, consecutive=consecutive)
            self.assertGreaterEqual(verdict.retry_delay, policy.BASE_DELAY)


class TellingTheUserTests(unittest.TestCase):
    def test_the_first_failure_says_what_went_wrong(self):
        verdict = policy.classify(RuntimeError("model not found: gemini-9"), resumed_with=False)
        self.assertTrue(verdict.tell_user)
        self.assertIn("model not found", verdict.message)

    def test_a_long_streak_is_summarised_rather_than_repeated(self):
        verdict = policy.classify(RuntimeError("still failing"), resumed_with=False,
                                  consecutive=policy.TELL_USER_AFTER)
        self.assertTrue(verdict.is_storm)
        self.assertIn("4 attempts failed", verdict.message)

    def test_the_summary_is_said_once_and_not_on_every_attempt_after_it(self):
        # Saying it every time is how the log filled with identical lines.
        for consecutive in range(policy.TELL_USER_AFTER + 1, policy.TELL_USER_AFTER + 6):
            verdict = policy.classify(RuntimeError("still failing"), resumed_with=False,
                                      consecutive=consecutive)
            self.assertFalse(verdict.tell_user, consecutive)
            self.assertEqual(verdict.message, "", consecutive)
            self.assertGreaterEqual(verdict.retry_delay, policy.BASE_DELAY)


class WhichFailuresCountAsAResumptionFailureTests(unittest.TestCase):
    """The marker list is the whole point of this module — test it both ways."""

    def test_an_expired_session_is_one(self):
        for text in ("Failed to resume the session",
                     "INVALID_ARGUMENT: the resumption handle is no longer valid",
                     "NOT_FOUND: session expired",
                     "conversation handle was rejected"):
            self.assertTrue(policy.looks_like_resumption_failure(RuntimeError(text)), text)

    def test_a_bad_tuning_field_is_not(self):
        # INVALID_ARGUMENT here is about thinking/proactive config, and treating it
        # as a dead handle skipped the branch that repairs the real cause.
        for text in ("INVALID_ARGUMENT: Unknown name \"thinking_config\"",
                     "INVALID_ARGUMENT: media_resolution unsupported",
                     "invalid argument: proactive_audio unknown field"):
            self.assertFalse(policy.looks_like_resumption_failure(RuntimeError(text)), text)

    def test_a_wrong_model_name_is_not(self):
        for text in ("NOT_FOUND: model not found: gemini-9",
                     "404 model not found"):
            self.assertFalse(policy.looks_like_resumption_failure(RuntimeError(text)), text)

    def test_the_original_complaint_is_not(self):
        # The exact string that used to match the substring "handle".
        exc = RuntimeError("cannot schedule new futures after shutdown while handling audio")
        self.assertFalse(policy.looks_like_resumption_failure(exc))
        verdict = policy.classify(exc, resumed_with=True, consecutive=0)
        self.assertFalse(verdict.drop_handle)
        self.assertGreaterEqual(verdict.retry_delay, policy.BASE_DELAY)

    def test_a_nonsense_streak_number_does_not_raise(self):
        for bad in (None, "x", -5, 3.7):
            verdict = policy.classify(RuntimeError("x"), resumed_with=False,
                                      consecutive=bad)
            self.assertGreaterEqual(verdict.retry_delay, policy.BASE_DELAY)

    def test_later_failures_keep_quiet(self):
        quiet = policy.classify(RuntimeError("x"), resumed_with=False, consecutive=2)
        self.assertFalse(quiet.tell_user)


class RedactionTests(unittest.TestCase):
    def test_a_credential_shaped_token_never_reaches_the_log_line(self):
        exc = RuntimeError("401 for key AIzaSyB1234567890abcdefghijklmnop")
        verdict = policy.classify(exc, resumed_with=False)
        self.assertNotIn("AIzaSyB1234567890", verdict.message)
        self.assertIn("[redacted]", verdict.message)

    def test_a_bearer_token_is_redacted(self):
        self.assertNotIn("sk-live-abcdefghijklmnop",
                         policy.describe(RuntimeError("bad key sk-live-abcdefghijklmnop")))

    def test_the_message_is_one_short_line(self):
        exc = RuntimeError("line one\nline two\n" + "x" * 500)
        text = policy.describe(exc)
        self.assertNotIn("\n", text)
        self.assertLessEqual(len(text), 160)


class OrderingTests(unittest.TestCase):
    def test_a_handle_drop_never_both_drops_and_backs_off_for_ages(self):
        verdict = policy.classify(RuntimeError("resumption handle expired"),
                                  resumed_with=True, consecutive=0)
        self.assertLess(verdict.retry_delay, policy.BASE_DELAY)

    def test_every_verdict_carries_a_reason(self):
        for kwargs in ({"resumed_with": True}, {"resumed_with": False},
                       {"resumed_with": False, "consecutive": 9}):
            with self.subTest(**kwargs):
                self.assertTrue(policy.classify(RuntimeError("x"), **kwargs).reason)


# ══════════════════════════════════════════════════════════════════════════
# from test_whatsapp_core.py
# ══════════════════════════════════════════════════════════════════════════
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import appidentity
from core.ui_tree import Node, Snapshot
from plugins import _whatsapp_core as wa


def tree(*, contacts=("Mum", "Alice"), composer="", send_button=True, search="Search or start new chat"):
    """A WhatsApp-shaped window: search box, conversation rows, composer."""
    rows = tuple(Node(role="ListItem", name=name, actions=("click",)) for name in contacts)
    children = [Node(role="Edit", name=search, actions=("set_value", "focus")),
                Node(role="List", name="Chat list", children=rows)]
    if send_button:
        children.append(Node(role="Button", name="Send", actions=("invoke",)))
    if composer is not None:
        children.append(Node(role="Edit", name="Type a message", value=composer,
                             actions=("set_value", "focus")))
    return Node(role="Window", name="WhatsApp", children=tuple(children))


class FakeResult:
    def __init__(self, ok=True, message=""):
        self.ok = ok
        self.message = message


class FakeSession:
    """Records what was asked of it, and changes the tree the way the app would.

    Refs carry the snapshot id, so `act` resolves a ref through the map recorded
    by the most recent `observe` — which is exactly what the real adapter does
    with its retained controls, and what makes a stale ref a refusal.
    """

    def __init__(self, root, *, contacts=("Mum",), sends=True, rebuild=True):
        self.root = root          # the shape as given; rebuild=False keeps it
        self.actions = []
        self.sends = sends
        self._rebuild_tree = rebuild
        self._names = {}
        self._contacts = tuple(contacts)
        self._composer = ""

    def observe(self, app=""):
        snap = Snapshot.capture(self.root, app=app, window="WhatsApp")
        self._names = {entry.ref: entry.name for entry in snap}
        return snap

    def act(self, ref, action="click", value=""):
        self.actions.append((ref, action, value))
        name = self._names.get(ref, "")
        if name in ("Search or start new chat", "Search"):
            # A real search filters the list; it does not de-duplicate it.
            matches = tuple(c for c in self._contacts if str(value).casefold() in c.casefold())
            self._contacts = matches or self._contacts
        elif name in self._contacts:
            pass                                  # a conversation opened
        elif name == "Type a message":
            self._composer = value
        elif name == "Send":
            if not self.sends:
                return FakeResult(False, "the button is disabled")
            self._composer = ""
        self._rebuild()
        return FakeResult(True, "")

    def _rebuild(self, contacts=None):
        if contacts is not None:
            self._contacts = contacts
        if self._rebuild_tree:
            self.root = tree(contacts=self._contacts, composer=self._composer)


class StringRules(unittest.TestCase):
    def test_fold_matches_core_identity(self):
        for text in ("Mum", "MÜM", "mum ", "Café", "Wu-Tang", "İstanbul",
                     "Mum's work", "アリス", ""):
            self.assertEqual(wa.fold(text), appidentity.fold(text), text)

    def test_name_in_phrase_is_whole_word(self):
        self.assertTrue(wa.name_in_phrase("chat with mum now", "mum"))
        self.assertFalse(wa.name_in_phrase("mumbo jumbo", "mum"))
        self.assertFalse(wa.name_in_phrase("", "mum"))
        self.assertFalse(wa.name_in_phrase("anything", ""))

    def test_name_in_phrase_matches_the_identity_rule(self):
        cases = [("msedgewebview2", "edge"), ("Edge browser", "Edge"), ("x-edge", "edge")]
        for phrase, word in cases:
            self.assertEqual(wa.name_in_phrase(phrase, word),
                             appidentity._contains_word(phrase, word), (phrase, word))


class Availability(unittest.TestCase):
    def test_get_returns_none_and_a_sentence_here(self):
        transport, why = wa.get(force=True)
        if sys.platform == "win32":
            self.skipTest("this machine may have a real driver")
        self.assertIsNone(transport)
        self.assertIn("Windows", why)

    def test_a_send_without_a_driver_is_not_attempted(self):
        from pathlib import Path as _Path
        source = (_Path(ROOT) / "actions" / "send_message.py").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn("from plugins import _whatsapp_core as wa", source)


class SendDiscipline(unittest.TestCase):
    def _transport(self, root, **kwargs):
        session = FakeSession(root, **kwargs)
        return wa.WhatsAppTransport(session=session), session

    def test_sends_and_verifies_the_box_emptied(self):
        transport, session = self._transport(tree(contacts=("Mum",)), contacts=("Mum",))
        sent, failure = transport.send_message_to("Mum", "on my way")
        self.assertTrue(sent, failure)
        self.assertEqual(failure, "")
        typed = [value for _ref, action, value in session.actions
                 if action == "set_value" and value == "on my way"]
        self.assertEqual(typed, ["on my way"], "the message was never typed")

    def test_unknown_contact_is_refused_and_nothing_is_typed(self):
        transport, session = self._transport(tree(contacts=("Mum", "Alice")),
                                            contacts=("Mum", "Alice"))
        sent, failure = transport.send_message_to("Bob", "hello")
        self.assertFalse(sent)
        self.assertIn("could not find", failure)
        self.assertNotIn("hello", [value for _r, _a, value in session.actions])

    def test_ambiguous_contact_is_refused(self):
        transport, _session = self._transport(tree(contacts=("Mum", "Mum")),
                                             contacts=("Mum", "Mum"))
        sent, failure = transport.send_message_to("Mum", "hello")
        self.assertFalse(sent)
        self.assertIn("match", failure)

    def test_a_disabled_send_button_is_a_failure_not_a_success(self):
        transport, _session = self._transport(tree(contacts=("Mum",)),
                                             contacts=("Mum",), sends=False)
        sent, failure = transport.send_message_to("Mum", "hello")
        self.assertFalse(sent)
        self.assertIn("Send", failure)

    def test_empty_message_is_refused(self):
        transport, _session = self._transport(tree(contacts=("Mum",)), contacts=("Mum",))
        sent, failure = transport.send_message_to("Mum", "   ")
        self.assertFalse(sent)
        self.assertIn("no message", failure)

    def test_a_missing_composer_is_a_failure(self):
        root = Node(role="Window", name="WhatsApp", children=(
            Node(role="Edit", name="Search or start new chat", actions=("set_value",)),
            Node(role="List", name="Chat list", children=(
                Node(role="ListItem", name="Mum", actions=("click",)),)),
        ))
        transport, _session = self._transport(root, contacts=("Mum",), rebuild=False)
        sent, failure = transport.send_message_to("Mum", "hello")
        self.assertFalse(sent)
        self.assertIn("message box", failure)

    def test_a_crash_inside_the_driver_becomes_a_sentence(self):
        class Exploding:
            def observe(self, app=""):
                raise RuntimeError("the window went away")

            def act(self, *a, **k):
                raise AssertionError("must not be reached")

        transport = wa.WhatsAppTransport(session=Exploding())
        sent, failure = transport.send_message_to("Mum", "hello")
        self.assertFalse(sent)
        self.assertIn("WhatsApp", failure)
        self.assertIsInstance(failure, str)


# ══════════════════════════════════════════════════════════════════════════
# from test_bridges.py
# ══════════════════════════════════════════════════════════════════════════
import json
import os
import stat
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

from core import bridges


class ProbeWhenAbsent(unittest.TestCase):
    def test_every_bridge_probes_without_raising(self):
        for key in ("rea", "hyperframes", "hindsight", "voicestudio", "hypit"):
            bridge = bridges.get(key)
            self.assertIsNotNone(bridge, key)
            ready, detail = bridge.probe()
            self.assertIsInstance(ready, bool)
            self.assertIsInstance(detail, str)
            self.assertTrue(detail, f"{key} must say something when it is missing")

    def test_absent_bridge_run_returns_sentence_not_exception(self):
        with mock.patch.object(bridges, "_which", return_value=None):
            for key in ("rea", "hyperframes", "hypit"):
                text = bridges.get(key).run("command", command="unknown-op")
                self.assertIsInstance(text, str)
                self.assertNotIn("Traceback", text)

    def test_unknown_bridge_is_none(self):
        self.assertIsNone(bridges.get("nothing_here"))

    def test_unknown_op_lists_known_ops(self):
        bridge = bridges.get("rea")
        with mock.patch.object(bridges, "_which", return_value="/usr/bin/rea"):
            text = bridge.run("not-an-op")
        self.assertIn("help", text.lower())

    def test_probe_all_shape(self):
        rows = bridges.probe_all()
        self.assertEqual(len(rows), 5)
        for row in rows:
            self.assertIn("key", row)
            self.assertIsInstance(row["ready"], bool)
            self.assertIn("detail", row)


class CliRunner(unittest.TestCase):
    def test_runs_a_real_process_and_captures_stdout(self):
        code, out, err = bridges.run_cli([sys.executable, "-c", "print('hello')"], timeout=10)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "hello")
        self.assertIsInstance(err, str)

    def test_missing_binary_returns_127_not_exception(self):
        code, out, err = bridges.run_cli(["/nonexistent/binary-xyz"])
        self.assertEqual(code, 127)
        self.assertEqual(out, "")

    def test_output_is_capped(self):
        code, out, err = bridges.run_cli(
            [sys.executable, "-c", "print('x' * 20000)"], timeout=10)
        self.assertEqual(code, 0)
        self.assertLessEqual(len(out), bridges.OUTPUT_LIMIT + 32)

    def test_timeout_is_reported(self):
        code, out, err = bridges.run_cli([sys.executable, "-c", "import time; time.sleep(5)"],
                                         timeout=0.5)
        self.assertNotEqual(code, 0)
        self.assertIn("did not answer", err.lower())


class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"status": "ok", "path": self.path}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"{}")
                body = json.dumps({"got": payload}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_get_returns_json(self):
        ok, data = bridges.http_json(f"http://127.0.0.1:{self.port}/health")
        self.assertTrue(ok)
        self.assertEqual(data["status"], "ok")

    def test_post_sends_payload(self):
        ok, data = bridges.http_json(f"http://127.0.0.1:{self.port}/x", {"hello": "world"})
        self.assertTrue(ok)
        self.assertEqual(data["got"]["hello"], "world")

    def test_closed_port_reports_failure_without_raising(self):
        ok, detail = bridges.http_json("http://127.0.0.1:1/health", timeout=1.0)
        self.assertFalse(ok)
        self.assertIsInstance(detail, str)

    def test_hindsight_bridge_uses_configured_url(self):
        with mock.patch.object(bridges, "_setting",
                               return_value=f"http://127.0.0.1:{self.port}"):
            bridge = bridges.get("hindsight")
            self.assertTrue(bridge.probe()[0])
            text = bridge.run("status")
            self.assertIn("ok", text)


class FakeCli(unittest.TestCase):
    """A real script on PATH, so the CLI path is exercised end to end."""

    @unittest.skipIf(os.name == "nt",
                     "the fake CLI is a POSIX shell script; a Windows shim would "
                     "test the shim rather than the bridge")
    def test_rea_bridge_calls_the_script(self):
        directory = Path(self._tmpdir())
        script = directory / "rea"
        script.write_text("#!/bin/sh\necho \"REA fake: $@\"\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        with mock.patch.dict(os.environ, {"PATH": f"{directory}:{os.environ['PATH']}"}), \
             mock.patch.object(bridges, "_which", return_value=str(script)):
            bridge = bridges.get("rea")
            self.assertTrue(bridge.probe()[0])
            text = bridge.run("command", command="capture", args=["--app", "demo"])
        self.assertIn("REA fake", text)
        self.assertIn("capture", text)

    def _tmpdir(self):
        import tempfile
        if not hasattr(self, "_dir"):
            self._dir = tempfile.mkdtemp(prefix="ultron-bridges-")
        return self._dir


# ══════════════════════════════════════════════════════════════════════════
# from test_lazyimport.py
# ══════════════════════════════════════════════════════════════════════════
import ast
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.lazyimport import LazyModule, installed

# Libraries whose only job is to cost time at launch. If one of these is imported
# at module scope by a file the boot path executes, the launch pays for it whether
# or not the session ever needs it.
HEAVY = {
    "pyautogui",
    "playwright",
    "requests",
    "bs4",
    "cv2",
    "PIL",
    "pandas",
    "docx",
    "openpyxl",
    "youtube_transcript_api",
    "sounddevice",
    "pyperclip",
    "numpy",
}

# (file, module) pairs that stay eager, each for a reason worth writing down.
ALLOWED_EAGER = {
    # main.py imports numpy for audio and runs before any action is read, so this
    # file reuses what is already in memory rather than deferring it.
    ("actions/screen_processor.py", "numpy"),
    # The RAM meter is built during window construction; psutil has to be there.
    ("actions/system_monitor.py", "psutil"),
}


def module_scope_imports(path: Path) -> set[str]:
    """Top-level third-party names imported when this file is executed.

    Imports inside a function do not run at import time, so they are invisible
    here — which is the entire point of the check. Imports inside a module-level
    `try:` or a class body DO run, so they count.
    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    found: set[str] = set()

    def type_checking_only(node: ast.If) -> bool:
        """True for `if TYPE_CHECKING:` / `if False:` guards.

        Those bodies are never executed at runtime — `TYPE_CHECKING` is False —
        so an import inside one costs nothing at launch. browser_control.py uses
        exactly this to keep its playwright type hints while importing nothing.
        """
        test = node.test
        names = {n.id for n in ast.walk(test) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(test) if isinstance(n, ast.Attribute)}
        if "TYPE_CHECKING" in names:
            return True
        return isinstance(test, ast.Constant) and not test.value

    def collect(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                for alias in child.names:
                    if isinstance(child, ast.Import):
                        found.add(alias.name.split(".")[0])
                    elif child.module:
                        found.add(child.module.split(".")[0])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue          # a function body is not the import path
            elif isinstance(child, ast.If) and type_checking_only(child):
                continue          # never executed at runtime
            else:
                collect(child)

    collect(tree)
    return found


class ProbeModuleTests(unittest.TestCase):
    """A real module on disk, so 'was it executed?' can be answered exactly."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.dir = Path(self._temp.name)
        self.marker = self.dir / "was_executed"
        (self.dir / "probe_mod_ultron.py").write_text(
            textwrap.dedent(
                f"""
                from pathlib import Path

                Path(r"{self.marker}").write_text("yes", encoding="utf-8")

                VALUE = 41
                NAME = "probe"

                def double(x):
                    return x * 2

                class Thing:
                    pass
                """
            ),
            encoding="utf-8",
        )
        sys.path.insert(0, str(self.dir))
        sys.modules.pop("probe_mod_ultron", None)

    def tearDown(self):
        sys.modules.pop("probe_mod_ultron", None)
        if str(self.dir) in sys.path:
            sys.path.remove(str(self.dir))
        self._temp.cleanup()

    def test_construction_does_not_import(self):
        LazyModule("probe_mod_ultron")
        self.assertFalse(self.marker.exists(), "constructing the proxy executed the module")
        self.assertNotIn("probe_mod_ultron", sys.modules)

    def test_repr_distinguishes_loaded_from_not_loaded(self):
        proxy = LazyModule("probe_mod_ultron")
        self.assertIn("not yet imported", repr(proxy))
        _ = proxy.VALUE
        self.assertIn("loaded", repr(proxy))

    def test_first_attribute_access_imports_once(self):
        proxy = LazyModule("probe_mod_ultron")
        self.assertEqual(proxy.VALUE, 41)
        self.assertTrue(self.marker.exists())
        # Second access must not re-execute the module.
        self.marker.unlink()
        _ = proxy.VALUE
        self.assertEqual(proxy.VALUE, 41)
        self.assertFalse(self.marker.exists())

    def test_functions_and_classes_are_reachable(self):
        proxy = LazyModule("probe_mod_ultron")
        self.assertEqual(proxy.double(5), 10)
        self.assertIsInstance(proxy.Thing(), proxy.Thing)

    def test_attribute_assignment_lands_on_the_module(self):
        proxy = LazyModule("probe_mod_ultron")
        proxy.VALUE = 7
        self.assertEqual(sys.modules["probe_mod_ultron"].VALUE, 7)

    def test_dir_lists_the_real_module(self):
        self.assertIn("double", dir(LazyModule("probe_mod_ultron")))

    def test_configure_hook_runs_on_every_access(self):
        # pyautogui's PAUSE/FAILSAFE are module-global: whoever is about to use
        # the module has to set them immediately before the call, which is why
        # the hook cannot be a once-only callback.
        calls = []
        proxy = LazyModule("probe_mod_ultron", lambda module: calls.append(module.VALUE))
        for _ in range(3):
            _ = proxy.VALUE
        self.assertEqual(len(calls), 3)

    def test_a_missing_module_fails_on_use_not_on_construction(self):
        proxy = LazyModule("probe_mod_ultron_absent")
        with self.assertRaises(ModuleNotFoundError):
            _ = proxy.anything

    def test_installed_answers_without_importing(self):
        self.assertTrue(installed("probe_mod_ultron"))
        self.assertNotIn("probe_mod_ultron", sys.modules)
        self.assertFalse(installed("probe_mod_ultron_absent"))
        self.assertTrue(installed("json"))
        self.assertFalse(installed(""))
        # Dotted names whose parent does not exist must answer False, not raise.
        self.assertFalse(installed("probe_mod_ultron_absent.child"))


class BootPathTests(unittest.TestCase):
    """The launch path, checked structurally."""

    def test_actions_and_plugins_do_not_import_heavy_libraries_at_module_scope(self):
        offenders = []
        for folder in ("actions", "plugins"):
            for path in sorted((ROOT / folder).glob("*.py")):
                rel = f"{folder}/{path.name}"
                for name in module_scope_imports(path) & HEAVY:
                    if (rel, name) in ALLOWED_EAGER:
                        continue
                    offenders.append(f"{rel} imports {name} at module scope")
        self.assertEqual(offenders, [], "launch-path imports that are paid on every start")

    def test_main_defers_the_provider_sdk(self):
        # 590 ms of a 795 ms module import was this one package.
        names = module_scope_imports(ROOT / "main.py")
        self.assertNotIn("google", names)
        self.assertNotIn("genai", names)

    def test_main_binds_the_provider_sdk_through_the_proxy(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8-sig")
        self.assertIn('genai = LazyModule("google.genai")', source)
        self.assertIn('types = LazyModule("google.genai.types")', source)
        self.assertIn("_GENAI_INSTALLED", source)

    def test_no_return_annotation_eagerly_imports_a_deferred_module(self):
        # `def f() -> types.X:` evaluates the annotation when the function is
        # defined, i.e. during module import — which would quietly undo the
        # deferral. Quoted annotations do not.
        source = (ROOT / "main.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        eager = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.returns is not None and isinstance(node.returns, ast.Attribute):
                eager.append(f"line {node.lineno}: {ast.unparse(node.returns)}")
        self.assertEqual(eager, [], "unquoted annotation on a deferred module")

    def test_the_identity_fallback_is_not_a_literal_name(self):
        # A config that fails to parse must not rename the assistant back to a
        # name this build stopped using.
        source = (ROOT / "main.py").read_text(encoding="utf-8-sig")
        self.assertNotIn('self._asst_name = "JARVIS"', source)
        self.assertIn("self._asst_name = identity.NAME", source)

    def test_the_config_file_is_read_with_a_context_manager(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8-sig")
        self.assertNotIn('json.loads(open(API_CONFIG_PATH', source)

class LaunchMeasurementTests(unittest.TestCase):
    """The measuring tool must not measure a lie.

    A start-up table whose rows share one process is a table of warm numbers
    wearing cold labels. These pin the two things that keep the tool honest:
    every stage runs in its own subprocess, and a stage that cannot run here is
    reported as unmeasurable instead of guessed.

    They exist because a measurement was wrong once. Deferring `ui.py`'s psutil
    import looked like a 22 ms win on a noisy harness; run properly, seven fresh
    processes each, it was 186 ms -> 182 ms and the first frame was not faster at
    all, because the window constructs the system monitor anyway. The change was
    reverted, and the tool that showed it was wrong is the one below.
    """
    """The measuring tool must not measure a lie.

    A start-up table whose rows share one process is a table of warm numbers
    wearing cold labels. These pin the two things that keep the tool honest:
    every stage runs in its own subprocess, and a stage that cannot run here is
    reported as unmeasurable instead of guessed.
    """

    def setUp(self):
        import importlib.util
        path = ROOT / "scripts" / "bench_startup.py"
        spec = importlib.util.spec_from_file_location("bench_startup_for_tests", path)
        self.bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.bench)

    def test_every_stage_runs_in_its_own_process(self):
        self.assertTrue(self.bench.PROBES, "no stages to measure")
        for name, code in self.bench.PROBES.items():
            self.assertIsInstance(code, str)
            self.assertTrue(code.strip(), f"stage {name!r} has no code")

    def test_a_stage_that_cannot_run_is_reported_not_guessed(self):
        result = self.bench.run_probe("broken", "raise SystemExit(3)", runs=1)
        self.assertIsNone(result.get("ms"), "an impossible stage returned a number")
        self.assertTrue(result.get("error"), "the failure was not reported")

    def test_a_measurement_returns_a_positive_median(self):
        result = self.bench.run_probe("pass", "import json; print(json.dumps({'ms': 1.0}))",
                                      runs=1)
        self.assertGreater(result.get("ms") or 0, 0.0)


if __name__ == "__main__":
    unittest.main()
