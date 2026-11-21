"""Dashboard fixes: the firewall repair script, and the upload route's order of checks.

Firewall (Windows branch, simulated on every platform)
    `_ensure_network_access` built `netsh ... delete rule name="..."` from the
    (rule name, program) PAIRS it was given, so it asked Windows to delete a rule
    called "('Python (blocked)', 'c:\\python312\\python.exe')". That matches nothing.
    The block that makes the phone unreachable was therefore never removed, while a
    comment said that line "actually fixes the connection". Its re-check afterwards
    read a list cached BEFORE the repair, so it could only ever report "still
    blocked", whatever the repair did.

Pairing
    `/login` limits wrong guesses per address; `/auto-login`, which takes the same
    one-time key, did not, so the limit protected the door nobody had to use.
    The TLS private key was written with the default mode and chmod-ed on the next
    line: readable by any local user for the time between the two.

Upload
    The route declared `file: UploadFile`, so FastAPI parsed and spooled the whole
    multipart body BEFORE the handler checked the token: 40 MB from a stranger was
    accepted first, then answered 401. The size limit was also applied only while
    copying out of that spool, after the whole body had already been received.
    And with python-multipart absent the dashboard could not be built at all,
    although a 503 fallback had been written for exactly that case.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import ctypes
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from core import failures
from dashboard import server

ROOT = Path(__file__).resolve().parent.parent
PYTHON = "C:\\Python312\\python.exe"


def netsh_block_listing(*names, program=PYTHON):
    """What `netsh advfirewall firewall show rule name=all dir=in verbose` prints."""
    return "".join(
        f"Rule Name:                            {name}\n"
        f"Program:                              {program}\n"
        f"Action:                               Block\n\n"
        for name in names
    )


class WindowsFirewallRepair(unittest.TestCase):
    """Run the Windows branch of `_ensure_network_access` with netsh and UAC faked."""

    def run_repair(self, listing_before, uac_fixes_it=True):
        """-> (the .bat text that would run elevated, what was printed)."""
        state = {"after_uac": False}
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            result = mock.MagicMock()
            result.returncode = 0
            result.stdout = ""
            if isinstance(cmd, list) and cmd[:1] == ["netsh"]:
                if "name=all" in cmd:                          # the block-rule scan
                    clean = "No rules match the specified criteria.\n"
                    result.stdout = clean if state["after_uac"] else listing_before
                else:                                          # does one rule exist?
                    result.stdout = "No rules match the specified criteria.\n"
                    result.returncode = 1
            elif isinstance(cmd, list) and cmd and str(cmd[0]).endswith(".bat"):
                result.returncode = 1                          # not admin: go through UAC
            return result

        def fake_shell_execute(_hwnd, _verb, path, *_rest):
            captured["bat"] = Path(path).read_text(encoding="utf-8")
            state["after_uac"] = uac_fixes_it
            return 42                                          # > 32 means "accepted"

        fake_windll = types.SimpleNamespace(
            shell32=types.SimpleNamespace(ShellExecuteW=fake_shell_execute))
        stand_in = lambda name: codecs.lookup("utf-8") if name == "mbcs" else None  # noqa: E731
        codecs.register(stand_in)                  # cmd.exe's code page; only Windows has it
        out = io.StringIO()
        real_exists = os.path.exists
        server._BLOCK_CACHE = None
        try:
            with mock.patch.object(sys, "platform", "win32"), \
                    mock.patch.object(ctypes, "windll", fake_windll, create=True), \
                    mock.patch.object(subprocess, "run", fake_run), \
                    mock.patch.object(sys, "executable", PYTHON), \
                    mock.patch.object(os.path, "exists",
                                      lambda p: False if str(p).endswith("pythonw.exe")
                                      else real_exists(p)), \
                    mock.patch.object(time, "sleep", lambda *_: None), \
                    contextlib.redirect_stdout(out):
                server._ensure_network_access(8000, 8001)
        finally:
            codecs.unregister(stand_in)
            server._BLOCK_CACHE = None
        return captured.get("bat", ""), out.getvalue()

    def test_the_batch_deletes_each_block_rule_by_its_name(self):
        bat, _ = self.run_repair(netsh_block_listing("Python (blocked by admin)"))
        deletes = [ln for ln in bat.splitlines() if "delete rule" in ln]
        self.assertIn('netsh advfirewall firewall delete rule '
                      'name="Python (blocked by admin)" dir=in', deletes)

    def test_no_delete_line_carries_a_tuple(self):
        bat, _ = self.run_repair(netsh_block_listing("Python (blocked by admin)"))
        for line in bat.splitlines():
            self.assertNotIn("('", line, line)
            self.assertNotIn("')", line, line)

    def test_a_rule_listed_for_both_interpreters_is_deleted_once(self):
        listing = (netsh_block_listing("Block Python", program=PYTHON)
                   + netsh_block_listing("Block Python", program=PYTHON))
        bat, _ = self.run_repair(listing)
        own = [ln for ln in bat.splitlines() if 'name="Block Python"' in ln]
        self.assertEqual(len(own), 1, own)

    def test_after_the_repair_the_check_reads_the_firewall_again(self):
        # The fake firewall is clean once the elevated script has "run".
        _, said = self.run_repair(netsh_block_listing("Python (blocked by admin)"))
        self.assertIn("Network setup complete", said)
        self.assertNotIn("STILL blocking", said)

    def test_when_the_repair_does_not_work_it_still_says_so(self):
        _, said = self.run_repair(netsh_block_listing("Python (blocked by admin)"),
                                  uac_fixes_it=False)
        self.assertIn("STILL blocking", said)
        self.assertNotIn("Network setup complete", said)
        self.assertIn("Python (blocked by admin)", said)

    def test_a_rule_name_with_shell_syntax_is_never_put_in_the_elevated_script(self):
        evil = 'x" & calc.exe & "'
        bat, said = self.run_repair(netsh_block_listing(evil, "Honest rule"))
        self.assertNotIn("calc.exe", bat)
        self.assertIn('name="Honest rule"', bat)
        self.assertIn("calc.exe", said, "the owner must be told which rule to delete by hand")

    def test_split_removable_rules(self):
        removable, by_hand = server._split_removable_rules([
            ("A", "p1"), ("A", "p2"), ("B%PATH%", "p1"), ("C", "p1"), ("D|E", "p1")])
        self.assertEqual(removable, ["A", "C"])
        self.assertEqual(by_hand, ["B%PATH%", "D|E"])

    def test_the_cached_answer_is_used_until_a_refresh_is_asked_for(self):
        calls = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(1)
            return mock.MagicMock(stdout=netsh_block_listing("Rule One"), returncode=0)

        server._BLOCK_CACHE = None
        try:
            with mock.patch.object(sys, "platform", "win32"), \
                    mock.patch.object(subprocess, "run", fake_run), \
                    mock.patch.object(sys, "executable", PYTHON), \
                    contextlib.redirect_stdout(io.StringIO()):
                first = server.blocking_firewall_rules()
                again = server.blocking_firewall_rules()
                fresh = server.blocking_firewall_rules(refresh=True)
        finally:
            server._BLOCK_CACHE = None
        self.assertEqual(first, [("Rule One", PYTHON.lower())])
        self.assertEqual((again, fresh), (first, first))
        self.assertEqual(len(calls), 2, "one scan, one cached read, one refreshed scan")


class MacosAllowScript(unittest.TestCase):
    FW = "/usr/libexec/ApplicationFirewall/socketfilterfw"

    @staticmethod
    def applescript_unescape(script: str) -> str:
        """Read the shell command back out of `do shell script "..." with ...`."""
        head, tail = 'do shell script "', '" with administrator privileges'
        assert script.startswith(head) and script.endswith(tail), script
        body, out, i = script[len(head):-len(tail)], [], 0
        while i < len(body):
            if body[i] == "\\":
                out.append(body[i + 1])
                i += 2
            else:
                assert body[i] != '"', f"an unescaped quote ends the AppleScript string: {script}"
                out.append(body[i])
                i += 1
        return "".join(out)

    def test_a_path_with_a_space_stays_one_shell_word(self):
        py = "/Users/Ana Ruiz/venv/bin/python"
        words = shlex.split(self.applescript_unescape(server._macos_allow_script(self.FW, py)))
        self.assertEqual(words, [self.FW, "--add", py, "&&", self.FW, "--unblockapp", py])

    def test_a_quote_in_the_path_cannot_end_the_applescript_string(self):
        py = '/tmp/a"b; rm -rf ~/python'
        words = shlex.split(self.applescript_unescape(server._macos_allow_script(self.FW, py)))
        self.assertEqual(words, [self.FW, "--add", py, "&&", self.FW, "--unblockapp", py])

    def test_a_backslash_survives(self):
        py = "/tmp/odd\\name/python"
        words = shlex.split(self.applescript_unescape(server._macos_allow_script(self.FW, py)))
        self.assertEqual(words[2], py)


# ── uploads ──────────────────────────────────────────────────────────────────

BOUNDARY = "xBOUNDARYx"


def multipart_head(filename="big.bin"):
    return (f"--{BOUNDARY}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n").encode("latin-1")


def multipart_tail():
    return f"\r\n--{BOUNDARY}--\r\n".encode("latin-1")


def upload_scope(token=None, content_length=None):
    headers = [(b"content-type", f"multipart/form-data; boundary={BOUNDARY}".encode())]
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    return {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "POST", "path": "/api/upload", "raw_path": b"/api/upload",
            "query_string": b"", "root_path": "", "scheme": "http",
            "headers": headers, "client": ("203.0.113.9", 5555), "server": ("testserver", 80)}


async def call_app(app, scope, receive):
    """Drive the ASGI app directly -> (status, body bytes)."""
    sent = []

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body


@unittest.skipUnless(server._DEPS_OK and server._UPLOAD_OK,
                     "fastapi and python-multipart are needed for the upload route")
class UploadRoute(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dashboard = server.DashboardServer()
        self.dashboard._uploads_dir = Path(self.temp.name)
        self.dashboard._tokens["good"] = time.time()
        self.dashboard._token_keys["good"] = "KEY"
        patcher = mock.patch.object(server, "MAX_UPLOAD_MB", 1)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.temp.cleanup)

    def uploaded(self):
        return sorted(p.name for p in Path(self.temp.name).iterdir())

    def test_a_stranger_is_refused_before_one_byte_of_the_body_is_read(self):
        async def receive():
            raise AssertionError("the body was read before the token was checked")

        for token in (None, "wrong"):
            status, body = asyncio.run(call_app(
                self.dashboard.app, upload_scope(token, content_length=40 * 1024 * 1024),
                receive))
            self.assertEqual(status, 401, token)
            self.assertIn(b"Unauthorized", body)
        self.assertEqual(self.uploaded(), [])

    def test_an_oversize_declared_length_is_refused_without_reading(self):
        async def receive():
            raise AssertionError("the body was read although its declared size is too big")

        status, body = asyncio.run(call_app(
            self.dashboard.app, upload_scope("good", content_length=50 * 1024 * 1024), receive))
        self.assertEqual(status, 413)
        self.assertIn(b"too large", body)

    def test_a_body_that_never_stops_is_cut_off_at_the_limit(self):
        # No Content-Length (chunked), so only the stream itself can be bounded.
        chunk = b"A" * 65536
        consumed = {"chunks": 0}
        head = multipart_head()

        async def receive():
            consumed["chunks"] += 1
            if consumed["chunks"] > 1000:
                raise AssertionError("the server kept reading an endless body")
            body = head + chunk if consumed["chunks"] == 1 else chunk
            return {"type": "http.request", "body": body, "more_body": True}

        status, body = asyncio.run(call_app(
            self.dashboard.app, upload_scope("good"), receive))
        self.assertEqual(status, 413)
        limit_chunks = (1024 * 1024 + server._MULTIPART_SLACK_BYTES) // 65536
        self.assertLessEqual(consumed["chunks"], limit_chunks + 3,
                             "it must stop soon after the limit, not at the end of the body")
        self.assertEqual(self.uploaded(), [])

    def test_a_file_over_the_exact_limit_is_refused_and_not_kept(self):
        data = b"B" * (1024 * 1024 + 10)                      # within the slack, over the limit
        payload = multipart_head() + data + multipart_tail()
        sent = {"done": False}

        async def receive():
            if sent["done"]:
                return {"type": "http.disconnect"}
            sent["done"] = True
            return {"type": "http.request", "body": payload, "more_body": False}

        status, _ = asyncio.run(call_app(self.dashboard.app, upload_scope("good"), receive))
        self.assertEqual(status, 413)
        self.assertEqual(self.uploaded(), [], "the partial file must be removed")

    def post_file(self, filename, data, token="good", part="file"):
        """POST one multipart file straight to the ASGI app -> (status, parsed JSON)."""
        head = (f"--{BOUNDARY}\r\n"
                f'Content-Disposition: form-data; name="{part}"; filename="{filename}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n").encode("latin-1")
        payload = head + data + multipart_tail()
        sent = {"done": False}

        async def receive():
            if sent["done"]:
                return {"type": "http.disconnect"}
            sent["done"] = True
            return {"type": "http.request", "body": payload, "more_body": False}

        status, body = asyncio.run(call_app(
            self.dashboard.app, upload_scope(token, content_length=len(payload)), receive))
        return status, json.loads(body)

    def test_a_normal_upload_still_works_and_is_sanitised(self):
        status, first = self.post_file("../../evil name?.txt", b"hello")
        self.assertEqual(status, 200, first)
        self.assertEqual(first["size"], 5)
        saved = first["name"]
        self.assertNotIn("/", saved)
        self.assertNotIn("..", saved)
        self.assertEqual((Path(self.temp.name) / saved).read_bytes(), b"hello")
        status, second = self.post_file("../../evil name?.txt", b"again")
        self.assertEqual(status, 200, second)
        self.assertNotEqual(second["name"], saved, "an existing file is never replaced")
        self.assertEqual((Path(self.temp.name) / saved).read_bytes(), b"hello")
        self.assertEqual(len(self.uploaded()), 2)

    def test_a_request_with_no_file_part_is_a_400(self):
        status, body = self.post_file("a.txt", b"x", part="not_the_file")
        self.assertEqual(status, 400, body)
        self.assertEqual(self.uploaded(), [])

    def test_two_uploads_of_one_name_can_never_share_a_file(self):
        # The old code checked `dest.exists()` and opened the path in a LATER step.
        first_path, first = server._create_unique(Path(self.temp.name), "same.txt")
        second_path, second = server._create_unique(Path(self.temp.name), "same.txt")
        third_path, third = server._create_unique(Path(self.temp.name), "same.txt")
        for handle in (first, second, third):
            handle.close()
        self.assertEqual(sorted(p.name for p in (first_path, second_path, third_path)),
                         ["same.txt", "same_1.txt", "same_2.txt"])


def get_scope(path, query=b"", client="203.0.113.9"):
    return {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "GET", "path": path, "raw_path": path.encode(),
            "query_string": query, "root_path": "", "scheme": "http",
            "headers": [], "client": (client, 5555), "server": ("testserver", 80)}


def post_scope(path, client="203.0.113.9"):
    scope = get_scope(path, client=client)
    scope["method"] = "POST"
    scope["headers"] = [(b"content-type", b"application/json")]
    return scope


@unittest.skipUnless(server._DEPS_OK, "fastapi is not installed")
class PairingKeyGuesses(unittest.TestCase):
    """`/login` and `/auto-login` take the same one-time key, so they share one budget."""

    GOOD = "GOODKEY2"

    def setUp(self):
        self.dashboard = server.DashboardServer()
        self.dashboard._pending_keys = {self.GOOD: time.time() + 600}

        async def quiet(_message):
            return None
        patcher = mock.patch.object(self.dashboard, "broadcast", quiet)
        patcher.start()
        self.addCleanup(patcher.stop)

    def auto_login(self, key, client="203.0.113.9"):
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def run():
            return await call_app(self.dashboard.app,
                                  get_scope("/auto-login", f"key={key}".encode(), client),
                                  receive)
        return asyncio.run(run())

    def login(self, pin, client="203.0.113.9"):
        body = json.dumps({"pin": pin}).encode()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def run():
            return await call_app(self.dashboard.app, post_scope("/login", client), receive)
        return asyncio.run(run())

    def test_a_wrong_key_is_not_a_session(self):
        status, body = self.auto_login("WRONGKEY")
        self.assertEqual(status, 200)
        self.assertIn(b"Link Expired", body)
        self.assertEqual(self.dashboard._tokens, {})
        self.assertIn(self.GOOD, self.dashboard._pending_keys, "a miss spends nothing")

    def test_guessing_is_cut_off_after_the_allowed_number(self):
        for _ in range(server._LOGIN_MAX_TRIES):
            self.assertEqual(self.auto_login("WRONGKEY")[0], 200)
        status, body = self.auto_login("WRONGKEY")
        self.assertEqual(status, 429)
        self.assertIn(b"Too many attempts", body)

    def test_a_blocked_address_is_refused_even_with_the_right_key(self):
        # If the right key worked while blocked, a guesser could keep going and
        # simply look at which answer is different.
        for _ in range(server._LOGIN_MAX_TRIES):
            self.auto_login("WRONGKEY")
        status, body = self.auto_login(self.GOOD)
        self.assertEqual(status, 429, body[:200])
        self.assertEqual(self.dashboard._tokens, {})
        self.assertIn(self.GOOD, self.dashboard._pending_keys, "and the key is not consumed")

    def test_another_address_is_not_punished_for_it(self):
        for _ in range(server._LOGIN_MAX_TRIES):
            self.auto_login("WRONGKEY", client="198.51.100.7")
        status, body = self.auto_login(self.GOOD, client="203.0.113.9")
        self.assertEqual(status, 200)
        self.assertNotIn(b"Link Expired", body)
        self.assertEqual(len(self.dashboard._tokens), 1)

    def test_the_right_key_works_once_and_forgives_earlier_slips(self):
        for _ in range(server._LOGIN_MAX_TRIES - 1):
            self.auto_login("WRONGKEY")
        status, body = self.auto_login(self.GOOD)
        self.assertEqual(status, 200)
        self.assertIn(b"jarvis_token", body)
        self.assertNotIn(self.GOOD, self.dashboard._pending_keys, "one-time use")
        self.assertEqual(self.dashboard._throttle.blocked_for("203.0.113.9"), 0.0)
        # The count starts again after a success, like /login: the same address can
        # slip the allowed number of times once more and still get in.
        self.dashboard._pending_keys["SECONDKEY"] = time.time() + 600
        for _ in range(server._LOGIN_MAX_TRIES - 1):
            self.auto_login("WRONGKEY")
        self.assertEqual(self.auto_login("SECONDKEY")[0], 200)
        self.assertEqual(len(self.dashboard._tokens), 2)

    def test_the_two_doors_share_one_budget(self):
        half = server._LOGIN_MAX_TRIES // 2
        for _ in range(half):
            self.assertEqual(self.login("WRONGKEY")[0], 401)
        for _ in range(server._LOGIN_MAX_TRIES - half):
            self.assertEqual(self.auto_login("WRONGKEY")[0], 200)
        self.assertEqual(self.auto_login("WRONGKEY")[0], 429)
        self.assertEqual(self.login("WRONGKEY")[0], 429)

    def test_login_itself_still_works(self):
        status, body = self.login(self.GOOD)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])


@unittest.skipUnless(os.name == "posix", "file modes are a POSIX idea")
class ThePrivateKeyIsNeverWorldReadable(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "jarvis.key"
        old = os.umask(0o022)       # the usual default: new files come out 0644
        self.addCleanup(os.umask, old)

    def mode(self):
        return self.path.stat().st_mode & 0o777

    def test_it_is_created_with_the_private_mode_not_changed_afterwards(self):
        # chmod made a no-op: if the mode is right, the CREATE set it. The old code,
        # which wrote the default mode and fixed it on the next line, fails here.
        with mock.patch.object(os, "chmod", lambda *a, **k: None):
            server._write_private(self.path, b"secret")
        self.assertEqual(self.mode(), 0o600)
        self.assertEqual(self.path.read_bytes(), b"secret")

    def test_the_old_write_then_chmod_really_did_leave_a_window(self):
        self.path.write_bytes(b"secret")
        self.assertEqual(self.mode(), 0o644, "what write_bytes alone leaves, with this umask")

    def test_an_existing_loose_file_is_tightened(self):
        self.path.write_bytes(b"old")
        self.path.chmod(0o644)
        server._write_private(self.path, b"new")
        self.assertEqual(self.mode(), 0o600)
        self.assertEqual(self.path.read_bytes(), b"new")

    def test_the_certificate_generator_uses_it(self):
        try:
            import cryptography  # noqa: F401
        except ImportError:
            self.skipTest("cryptography is not installed")
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(server, "BASE_DIR", Path(folder)), \
                mock.patch.object(os, "chmod", lambda *a, **k: None):
            self.assertTrue(server._ensure_certs())
            key = Path(folder) / "config" / "certs" / "jarvis.key"
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertTrue((Path(folder) / "config" / "certs" / "jarvis.crt").is_file())


def websocket_scope(path, query=b"", client="203.0.113.9"):
    return {"type": "websocket", "asgi": {"version": "3.0"}, "path": path,
            "raw_path": path.encode(), "query_string": query, "root_path": "",
            "scheme": "ws", "headers": [], "client": (client, 5555), "server": ("testserver", 80),
            "subprotocols": []}


async def websocket_session(app, scope, frames):
    """Connect, send each frame ({"text": ..} or {"bytes": ..}), hang up -> what the app sent."""
    incoming = asyncio.Queue()
    sent = []
    incoming.put_nowait({"type": "websocket.connect"})
    for frame in frames:
        incoming.put_nowait({"type": "websocket.receive", **frame})
    incoming.put_nowait({"type": "websocket.disconnect", "code": 1000})

    async def receive():
        return await incoming.get()

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return sent


class WithADashboard(unittest.TestCase):
    """A dashboard with one live token (`good`) and one unused pairing key."""

    def setUp(self):
        self.dashboard = server.DashboardServer()
        self.dashboard._tokens["good"] = time.time()
        self.dashboard._token_keys["good"] = "KEY12345"
        self.dashboard._pending_keys = {"GOODKEY2": time.time() + 600}

        async def quiet(_message):
            return None
        patcher = mock.patch.object(self.dashboard, "broadcast", quiet)
        patcher.start()
        self.addCleanup(patcher.stop)
        failures.clear()
        self.addCleanup(failures.clear)

    def send_body(self, path, body=b"", token=None, client="203.0.113.9", messages=None,
                  length="auto"):
        """POST `body` (or the exact ASGI `messages`) -> (status, response bytes)."""
        headers = [(b"content-type", b"application/json")]
        if token:
            headers.append((b"authorization", f"Bearer {token}".encode()))
        if length == "auto":
            headers.append((b"content-length", str(len(body)).encode()))
        elif length is not None:
            headers.append((b"content-length", str(length).encode()))
        scope = post_scope(path, client)
        scope["headers"] = headers
        script = list(messages) if messages is not None else [
            {"type": "http.request", "body": body, "more_body": False}]

        async def receive():
            return script.pop(0) if script else {"type": "http.disconnect"}

        return asyncio.run(call_app(self.dashboard.app, scope, receive))

    def fetch(self, path, query=b""):
        async def receive():
            await asyncio.sleep(30)           # a client that stays connected
            return {"type": "http.disconnect"}

        return asyncio.run(call_app(self.dashboard.app, get_scope(path, query), receive))


JUNK_BODIES = {
    "empty": b"",
    "not json": b"\xff\xfe\x00not json{{{",
    "a list": b"[1, 2]",
    "a string": b'"pin"',
    "a number": b"5",
    "null": b"null",
    "nested past the parser": b"[" * 20000 + b"]" * 20000,
}


@unittest.skipUnless(server._DEPS_OK, "fastapi is not installed")
class JsonBodiesNeverRaise(WithADashboard):
    """A stranger's malformed body used to be an unhandled exception (a 500 and a traceback)."""

    ROUTES = (("/login", None), ("/api/device-login", None), ("/api/command", "good"))

    def test_every_malformed_body_is_a_400_not_an_exception(self):
        for path, token in self.ROUTES:
            for label, body in JUNK_BODIES.items():
                with self.subTest(route=path, body=label):
                    status, answer = self.send_body(path, body, token, client=f"198.51.100.{len(label)}")
                    self.assertEqual(status, 400, answer)

    def test_a_body_over_the_cap_is_a_413_without_reading_it(self):
        for path, token in self.ROUTES:
            with self.subTest(route=path):
                status, _ = self.send_body(path, b"x", token, length=server.MAX_JSON_BYTES + 1,
                                           client="198.51.100.77")
                self.assertEqual(status, 413)

    def test_a_body_that_never_declares_its_size_is_cut_off_at_the_cap(self):
        chunk = b" " * 16384
        messages = [{"type": "http.request", "body": chunk, "more_body": True}
                    for _ in range(8)]                                        # 128 KB
        for path, token in self.ROUTES:
            with self.subTest(route=path):
                status, _ = self.send_body(path, messages=list(messages), token=token,
                                           length=None, client="198.51.100.78")
                self.assertEqual(status, 413)

    def test_a_sender_that_hangs_up_half_way_is_a_400(self):
        half = [{"type": "http.request", "body": b'{"pin": "GOO', "more_body": True},
                {"type": "http.disconnect"}]
        for path, token in self.ROUTES:
            with self.subTest(route=path):
                status, _ = self.send_body(path, messages=list(half), token=token,
                                           client="198.51.100.79")
                self.assertEqual(status, 400)

    def test_a_body_just_under_the_cap_is_still_read(self):
        padding = "x" * (server.MAX_JSON_BYTES - 40)
        status, _ = self.send_body("/login", json.dumps({"pin": "NOPE", "pad": padding}).encode()[:server.MAX_JSON_BYTES])
        self.assertEqual(status, 401, "valid JSON within the cap reaches the key check")

    def test_malformed_logins_cost_an_attempt_like_wrong_keys(self):
        for _ in range(server._LOGIN_MAX_TRIES):
            self.assertEqual(self.send_body("/login", b"garbage")[0], 400)
        status, said = self.send_body("/login", json.dumps({"pin": "GOODKEY2"}).encode())
        self.assertEqual(status, 429, said)
        self.assertEqual(self.dashboard._tokens.keys(), {"good"}, "no new session was issued")

    def test_a_good_login_and_a_good_command_still_work(self):
        status, said = self.send_body("/login", json.dumps({"pin": "goodkey2"}).encode())
        self.assertEqual(status, 200, said)
        self.assertTrue(json.loads(said)["ok"])
        status, said = self.send_body("/api/command", json.dumps({"text": "  open notes  "}).encode(), "good")
        self.assertEqual(status, 200, said)
        self.assertEqual(self.dashboard._command_queue.get_nowait(), "open notes")

    def test_wrongly_typed_fields_are_refused_not_crashed_on(self):
        for payload in ({"text": 5}, {"enc": 5}, {"text": ["a"]}, {"enc": {"a": 1}}):
            with self.subTest(payload=payload):
                status, said = self.send_body("/api/command", json.dumps(payload).encode(), "good")
                self.assertEqual(status, 400, said)
        self.assertTrue(self.dashboard._command_queue.empty())

    def test_a_device_token_of_the_wrong_type_is_just_unknown(self):
        for payload in ({"device_token": 5}, {"device_token": None}, {"device_token": ["x"]}, {}):
            with self.subTest(payload=payload):
                status, _ = self.send_body("/api/device-login", json.dumps(payload).encode())
                self.assertEqual(status, 401)

    def test_an_unauthenticated_command_is_still_refused_before_its_body_is_read(self):
        status, _ = self.send_body("/api/command", b"[", messages=[])
        self.assertEqual(status, 401)


@unittest.skipUnless(server._DEPS_OK, "fastapi is not installed")
class TheWebSocketsSurviveBadFrames(WithADashboard):
    """An authenticated client that sent anything but a command object dropped its own socket."""

    def test_the_command_socket_ignores_what_is_not_a_command_and_keeps_going(self):
        frames = [
            {"text": "this is not json"},
            {"bytes": b"\x00\x01\x02"},
            {"text": "[1, 2, 3]"},
            {"text": "42"},
            {"text": json.dumps({"type": "command", "text": 5})},
            {"text": json.dumps({"type": "command", "enc": 5})},
            {"text": json.dumps({"type": "something else", "text": "ignored"})},
            {"text": json.dumps({"type": "command", "text": "  hello  "})},
        ]
        sent = asyncio.run(websocket_session(
            self.dashboard.app, websocket_scope("/ws", b"token=good"), frames))
        self.assertIn("websocket.accept", [m["type"] for m in sent])
        queued = []
        while not self.dashboard._command_queue.empty():
            queued.append(self.dashboard._command_queue.get_nowait())
        self.assertEqual(queued, ["hello"], "only the one real command reached the assistant")
        self.assertEqual(self.dashboard._clients, set(), "and the socket was cleaned up")
        noted = [n for n in failures.recent() if n["where"] == "dashboard.ws"]
        self.assertEqual(len(noted), 1, "one note for the whole connection, not one per frame")
        self.assertIn("6 malformed", noted[0]["error"])

    def test_a_stranger_is_closed_not_served(self):
        sent = asyncio.run(websocket_session(
            self.dashboard.app, websocket_scope("/ws", b"token=nope"), [{"text": "{}"}]))
        self.assertEqual(sent[0]["type"], "websocket.close")
        self.assertEqual(sent[0]["code"], 4001)

    def test_the_audio_socket_ignores_a_text_frame(self):
        frames = [{"text": "not audio"}, {"bytes": b"pcm-1"}, {"text": "still not"}, {"bytes": b"pcm-2"}]
        asyncio.run(websocket_session(
            self.dashboard.app, websocket_scope("/ws/phone-audio", b"token=good"), frames))
        got = []
        while not self.dashboard._phone_audio_queue.empty():
            got.append(self.dashboard._phone_audio_queue.get_nowait()["data"])
        self.assertEqual(got, [b"pcm-1", b"pcm-2"])
        noted = [n for n in failures.recent() if n["where"] == "dashboard.phone_audio"]
        self.assertEqual(len(noted), 1)
        self.assertIn("2 text", noted[0]["error"])


class InsideTheUploadsFolder(unittest.TestCase):
    """`server._inside`: a download name resolves to a file directly in the uploads folder or to
    nothing. It is a plain function, so these run without FastAPI installed."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.uploads = self.root / "uploads"
        self.uploads.mkdir()
        (self.uploads / "photo.txt").write_text("the photo", encoding="utf-8")
        (self.root / "secret.txt").write_text("not for download", encoding="utf-8")
        (self.uploads / "folder").mkdir()

    def test_a_file_in_the_folder_is_found(self):
        found = server._inside(self.uploads, "photo.txt")
        self.assertEqual(found, (self.uploads / "photo.txt").resolve())

    def test_dot_dot_a_folder_a_missing_name_and_a_nul_byte_are_all_none(self):
        for name in ("..", ".", "folder", "missing.txt", "a\x00b", "", "../secret.txt"):
            with self.subTest(name=name):
                self.assertIsNone(server._inside(self.uploads, name))

    def test_a_symlink_that_leads_out_is_none(self):
        link = self.uploads / "link.txt"
        try:
            link.symlink_to(self.root / "secret.txt")
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are not available here")
        self.assertIsNone(server._inside(self.uploads, "link.txt"))

    def test_on_windows_a_drive_relative_name_would_ignore_the_folder(self):
        # The hazard the check exists for, shown with the Windows path rules on any platform:
        # joining a name that starts with a drive letter does not append it.
        from pathlib import PureWindowsPath
        joined = PureWindowsPath("uploads") / "C:main.py"
        self.assertEqual(joined, PureWindowsPath("C:main.py"))
        self.assertFalse(joined.is_relative_to(PureWindowsPath("uploads")))


@unittest.skipUnless(server._DEPS_OK, "fastapi is not installed")
class DownloadRoute(WithADashboard):
    def setUp(self):
        super().setUp()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.uploads = Path(folder.name) / "uploads"
        self.uploads.mkdir()
        (self.uploads / "photo.txt").write_text("the photo", encoding="utf-8")
        (self.uploads / "folder").mkdir()
        self.dashboard._uploads_dir = self.uploads

    def test_the_route_serves_a_real_file_and_refuses_the_rest(self):
        status, body = self.fetch("/uploads/photo.txt", b"token=good")
        self.assertEqual((status, body), (200, b"the photo"))
        self.assertEqual(self.fetch("/uploads/photo.txt", b"token=nope")[0], 401)
        self.assertEqual(self.fetch("/uploads/missing.txt", b"token=good")[0], 404)
        self.assertEqual(self.fetch("/uploads/..", b"token=good")[0], 404)
        self.assertEqual(self.fetch("/uploads/folder", b"token=good")[0], 404)


class TheModuleDescribesItselfTruthfully(unittest.TestCase):
    """It said "HTTPS on port 8000 ... generated on first run" and headed its crypto section
    "AES-256-CBC": HTTPS is opt-in (`dashboard_https`), loopback HTTP is the default, and the
    code uses AES-GCM (the same file explains why CBC was replaced)."""

    def test_the_docstring_matches_the_defaults(self):
        doc = server.__doc__ or ""
        self.assertIn("AES-256-GCM", doc)
        self.assertNotIn("HTTPS on port 8000", doc)
        self.assertIn("opt-in", doc)
        self.assertIn("127.0.0.1", doc)
        self.assertIn("in clear", doc, "plain HTTP has no encryption layer; the page must say so")

    def test_the_crypto_section_is_not_headed_with_the_cipher_it_replaced(self):
        source = (ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("# ── AES-256-CBC", source)
        self.assertIn("AESGCM", source)

    def test_https_is_off_unless_the_settings_ask_for_it_and_a_certificate_exists(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "config").mkdir()
            with mock.patch.object(server, "BASE_DIR", base):
                self.assertFalse(server.DashboardServer._ssl_enabled(), "no settings file")
                (base / "config" / "api_keys.json").write_text('{"dashboard_https": true}',
                                                               encoding="utf-8")
                self.assertFalse(server.DashboardServer._ssl_enabled(), "no certificate yet")
                (base / "config" / "certs").mkdir()
                (base / "config" / "certs" / "jarvis.key").write_text("k", encoding="utf-8")
                (base / "config" / "certs" / "jarvis.crt").write_text("c", encoding="utf-8")
                self.assertTrue(server.DashboardServer._ssl_enabled())
                (base / "config" / "api_keys.json").write_text('{"dashboard_https": false}',
                                                               encoding="utf-8")
                self.assertFalse(server.DashboardServer._ssl_enabled(), "off unless asked for")


class WithoutPythonMultipart(unittest.TestCase):
    """The dashboard must still be built when the optional package is missing."""

    SCRIPT = r'''
import sys
sys.modules["python_multipart"] = None      # what "not installed" looks like to import
sys.modules["multipart"] = None
sys.path.insert(0, sys.argv[1])
import dashboard.server as server
assert server._DEPS_OK, "fastapi itself is missing"
assert server._UPLOAD_OK is False, "uploads must be reported unavailable"
app = server.DashboardServer().app          # used to raise RuntimeError here
import asyncio, json
sent = []
async def receive():
    return {"type": "http.request", "body": b"", "more_body": False}
async def send(message):
    sent.append(message)
scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
         "path": "/api/upload", "raw_path": b"/api/upload", "query_string": b"",
         "root_path": "", "scheme": "http", "headers": [],
         "client": ("203.0.113.9", 5555), "server": ("testserver", 80)}
asyncio.run(app(scope, receive, send))
status = next(m["status"] for m in sent if m["type"] == "http.response.start")
body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
assert status == 503, status
assert "python-multipart" in json.loads(body)["error"], body
print("FALLBACK-OK")
'''

    def test_the_dashboard_builds_and_uploads_answer_503(self):
        if not server._DEPS_OK:
            self.skipTest("fastapi is not installed")
        proc = subprocess.run(
            [sys.executable, "-c", self.SCRIPT, str(ROOT)], cwd=ROOT,
            capture_output=True, text=True, timeout=120, check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "QT_QPA_PLATFORM": "offscreen"})
        self.assertIn("FALLBACK-OK", proc.stdout, proc.stdout[-500:] + proc.stderr[-1500:])


if __name__ == "__main__":
    unittest.main()
