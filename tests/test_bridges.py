"""Tests for core.bridges — the five third-party integrations.

The important case is the one that is easy to skip: the tool is NOT installed.
A bridge that crashes, or claims success, when its dependency is absent is worse
than no bridge, because the model then tells the user something false.
"""

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
        code, out, err = bridges.run_cli(["python3", "-c", "print('hello')"], timeout=10)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "hello")
        self.assertIsInstance(err, str)

    def test_missing_binary_returns_127_not_exception(self):
        code, out, err = bridges.run_cli(["/nonexistent/binary-xyz"])
        self.assertEqual(code, 127)
        self.assertEqual(out, "")

    def test_output_is_capped(self):
        code, out, err = bridges.run_cli(
            ["python3", "-c", "print('x' * 20000)"], timeout=10)
        self.assertEqual(code, 0)
        self.assertLessEqual(len(out), bridges.OUTPUT_LIMIT + 32)

    def test_timeout_is_reported(self):
        code, out, err = bridges.run_cli(["python3", "-c", "import time; time.sleep(5)"],
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


if __name__ == "__main__":
    unittest.main()
