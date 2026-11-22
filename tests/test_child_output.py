"""A background program's output is logged, not thrown away.

AGENTS.md: "Never send a child process's output to `DEVNULL` without logging it". Three
places that start a long-lived program did exactly that, and each one reports failure as a
bare "not running":

* `core/sidecar.py` — the Go supervisor. Its start failure was `except Exception: return
  None`, so a binary that could not start looked identical to one that was never built.
* `core/llm_client.py` and `custom_jarvis/local_fallback.py` — `ollama serve`. When it dies
  on start (a port taken, a damaged model folder) the owner is told "Ollama did not
  respond" and the one file that says why was DEVNULL.

`core.crash.child_log` opens `logs/child-<name>.log` for them. These tests start real
child processes (a shell script standing in for the binary) and read what they wrote.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from core import crash, failures, llm_client, sidecar
from custom_jarvis import local_fallback

POSIX = os.name != "nt"


class WithAScratchRoot(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        patcher = mock.patch.dict(crash._state, {"root": self.root})
        patcher.start()
        self.addCleanup(patcher.stop)
        failures.clear()
        self.addCleanup(failures.clear)

    def log_text(self, name: str) -> str:
        path = crash.child_log_path(name)
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


class TheChildLog(WithAScratchRoot):
    def test_it_opens_a_file_in_the_logs_folder_with_a_dated_header(self):
        handle = crash.child_log("demo")
        self.assertIsNotNone(handle)
        handle.write(b"hello\n")
        handle.close()
        path = self.root / "logs" / "child-demo.log"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("demo started", text)
        self.assertIn("hello", text)

    def test_each_start_appends_so_an_earlier_failure_is_still_there(self):
        for line in (b"first run died\n", b"second run died\n"):
            handle = crash.child_log("demo")
            handle.write(line)
            handle.close()
        text = self.log_text("demo")
        self.assertIn("first run died", text)
        self.assertIn("second run died", text)
        self.assertEqual(text.count("demo started"), 2)

    def test_a_log_over_the_limit_is_cut_before_the_next_start(self):
        path = crash.child_log_path("demo")
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x" * (crash.CHILD_LOG_MAX + 10))
        handle = crash.child_log("demo")
        handle.close()
        self.assertLess(path.stat().st_size, 1000, "the old, oversized content is gone")

    def test_a_name_cannot_point_outside_the_logs_folder(self):
        for name in ("../../evil", "..\\..\\evil", "/etc/passwd", "a/b", "", None,
                     "x" * 300):
            with self.subTest(name=name):
                path = crash.child_log_path(name)
                self.assertEqual(path.parent, self.root / "logs")
                self.assertTrue(path.name.startswith("child-"))
                self.assertLess(len(path.name), 60)

    def test_a_folder_that_cannot_be_made_is_recorded_and_answers_none(self):
        blocker = self.root / "blocked"
        blocker.write_text("a file where a folder is needed", encoding="utf-8")
        with mock.patch.dict(crash._state, {"root": blocker}):
            self.assertIsNone(crash.child_log("demo"))
        self.assertTrue(any(n["where"] == "crash.child_log" for n in failures.recent()))


@unittest.skipUnless(POSIX, "stands in for the binary with a shell script")
class TheSidecarsOwnWordsAreKept(WithAScratchRoot):
    def make_binary(self, body: str) -> Path:
        path = self.root / "fake-watchd"
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def start(self, binary: Path):
        events = self.root / "events.jsonl"
        with mock.patch.dict(os.environ, {"ULTRON_SIDECAR": str(binary)}):
            return sidecar.try_start(["sleep"], events)

    def wait_for_exit(self, feed):
        deadline = time.time() + 5
        while feed.alive and time.time() < deadline:
            time.sleep(0.02)
        self.assertFalse(feed.alive)

    def test_what_the_supervisor_prints_and_what_it_complains_about_are_on_disk(self):
        feed = self.start(self.make_binary(
            "#!/bin/sh\necho watching-the-table\necho cannot-open-the-events-file >&2\nexit 3\n"))
        self.assertIsNotNone(feed)
        self.wait_for_exit(feed)
        text = self.log_text("watchd")
        self.assertIn("watching-the-table", text)
        self.assertIn("cannot-open-the-events-file", text, "stderr is kept too")
        self.assertEqual(feed.process.returncode, 3)

    def test_a_binary_that_cannot_start_is_noted_and_the_fallback_still_applies(self):
        feed = self.start(self.make_binary("#!/no/such/interpreter\n"))
        self.assertIsNone(feed, "main.py falls back to the Python watcher on None")
        notes = [n for n in failures.recent() if n["where"] == "sidecar.try_start"]
        self.assertEqual(len(notes), 1, "the reason is on the record, not nowhere")

    def test_no_binary_is_still_a_quiet_none(self):
        with mock.patch.dict(os.environ, {"ULTRON_SIDECAR": str(self.root / "absent")}):
            self.assertIsNone(sidecar.try_start(["sleep"], self.root / "e.jsonl"))
        self.assertEqual(failures.recent(), [], "an absent optional binary is not a failure")

    def test_the_log_handle_is_not_left_open_in_this_process(self):
        before = len(os.listdir("/proc/self/fd")) if os.path.isdir("/proc/self/fd") else None
        feed = self.start(self.make_binary("#!/bin/sh\nexit 0\n"))
        self.wait_for_exit(feed)
        feed.process.wait()
        if before is not None:
            self.assertLessEqual(len(os.listdir("/proc/self/fd")), before + 1)


class OllamaIsStartedWithItsOutputKept(WithAScratchRoot):
    def popen_calls(self, run):
        calls = []

        def fake_popen(command, **kwargs):
            calls.append((command, kwargs))
            return mock.Mock()
        with mock.patch.object(subprocess, "Popen", fake_popen):
            run()
        return calls

    def test_the_fallback_starts_it_with_a_log_not_devnull(self):
        with mock.patch.object(local_fallback.shutil, "which", return_value="/usr/bin/ollama"), \
                mock.patch.object(local_fallback, "running", return_value=False), \
                mock.patch.object(local_fallback, "START_WAIT", 0.0):
            calls = self.popen_calls(local_fallback.start_server)
        self.assertEqual(len(calls), 1)
        command, kwargs = calls[0]
        self.assertEqual(command, ["/usr/bin/ollama", "serve"])
        self.assertNotEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.STDOUT)
        self.assertTrue(crash.child_log_path("ollama").exists())

    def test_a_start_that_fails_is_noted(self):
        def refuse(*_args, **_kwargs):
            raise PermissionError("not allowed")
        with mock.patch.object(local_fallback.shutil, "which", return_value="/usr/bin/ollama"), \
                mock.patch.object(local_fallback, "running", return_value=False), \
                mock.patch.object(subprocess, "Popen", refuse):
            self.assertFalse(local_fallback.start_server())
        notes = [n for n in failures.recent() if n["where"] == "local_fallback.start_server"]
        self.assertEqual(len(notes), 1)
        self.assertIn("not allowed", notes[0]["error"])

    def test_the_llm_client_starts_it_with_a_log_not_devnull(self):
        class Down:
            status_code = 503

        def run():
            with mock.patch.object(llm_client, "get_llm_settings",
                                   return_value=("http://127.0.0.1:1", "m")), \
                    mock.patch.object(llm_client, "get_llm_provider", return_value="ollama"), \
                    mock.patch.object(llm_client.requests, "get", return_value=Down()), \
                    mock.patch.object(llm_client.time, "sleep"):
                clock = iter(range(0, 100000, 10))
                with mock.patch.object(llm_client.time, "time", lambda: next(clock)):
                    self.assertFalse(llm_client.ensure_ollama_running(timeout=1))

        calls = self.popen_calls(run)
        self.assertEqual(len(calls), 1)
        command, kwargs = calls[0]
        self.assertEqual(command, ["ollama", "serve"])
        self.assertNotEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.STDOUT)

    def test_without_a_writable_log_it_still_starts_and_says_why_it_is_blind(self):
        # The log is a convenience; being unable to open it must not stop the server.
        blocker = self.root / "blocked"
        blocker.write_text("x", encoding="utf-8")
        with mock.patch.dict(crash._state, {"root": blocker}), \
                mock.patch.object(local_fallback.shutil, "which", return_value="/usr/bin/ollama"), \
                mock.patch.object(local_fallback, "running", return_value=False), \
                mock.patch.object(local_fallback, "START_WAIT", 0.0):
            calls = self.popen_calls(local_fallback.start_server)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["stdout"], subprocess.DEVNULL)
        self.assertTrue(any(n["where"] == "crash.child_log" for n in failures.recent()),
                        "that is the recorded reason the output is not kept")


class NoOtherLongLivedChildOfTheCoreIsBlind(unittest.TestCase):
    """The three launches this file fixes must not regress to DEVNULL-only."""

    def test_the_sources_open_a_child_log(self):
        root = Path(__file__).resolve().parents[1]
        for relative in ("core/sidecar.py", "core/llm_client.py",
                         "custom_jarvis/local_fallback.py"):
            with self.subTest(file=relative):
                source = (root / relative).read_text(encoding="utf-8")
                self.assertIn("crash.child_log(", source)


if __name__ == "__main__":
    sys.exit(unittest.main())
