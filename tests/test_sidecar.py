"""tests/test_sidecar.py — the compiled part must never be a hard requirement.

The sidecar is the only component here that needs a Go toolchain, so the tests
have one job above all others: **prove that its absence changes nothing.** A
machine with no compiler, a machine whose binary was deleted, and a machine where
the binary dies mid-run must all end up on the Python watcher, watching.

The parsing tests matter for a second reason: the sidecar writes JSON lines and
the reader tails them. A half-written line is normal, not exceptional, and a
reader that assumes atomic writes would one day read half a record and report a
job that never finished.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import sidecar
from core.process_watch import Completion

ROOT = Path(__file__).resolve().parents[1]


class BinaryDiscovery(unittest.TestCase):
    def test_a_missing_binary_is_none_not_an_exception(self):
        with mock.patch.dict(os.environ, {"ULTRON_SIDECAR": "/nowhere/watchd"}, clear=False):
            self.assertIsNone(sidecar.binary_path())

    def test_an_override_that_exists_is_used(self):
        with tempfile.NamedTemporaryFile() as handle:
            with mock.patch.dict(os.environ, {"ULTRON_SIDECAR": handle.name}, clear=False):
                self.assertEqual(sidecar.binary_path(), Path(handle.name))

    def test_the_default_name_follows_the_platform(self):
        with mock.patch.dict(os.environ, {"ULTRON_SIDECAR": ""}, clear=False):
            found = sidecar.binary_path()
        expected = ROOT / "sidecar" / "bin" / (
            "watchd-windows.exe" if os.name == "nt" else "watchd-linux")
        self.assertEqual(found, expected if expected.exists() else None)


class EventParsing(unittest.TestCase):
    def test_a_finished_job_becomes_a_completion(self):
        done = sidecar.completion_from_event(
            {"pid": 42, "name": "antigravity", "seconds": 90.5, "how": "ended",
             "watch": "antigravity"})
        self.assertIsInstance(done, Completion)
        self.assertEqual(done.label, "antigravity")
        self.assertAlmostEqual(done.seconds, 90.5)
        self.assertIsNone(done.exit_code)
        self.assertIn("finished", done.sentence())

    def test_a_malformed_line_is_skipped_not_fatal(self):
        self.assertIsNone(sidecar.completion_from_event({}))
        self.assertIsNone(sidecar.completion_from_event(
            {"pid": "not a number", "name": "x"}))

    def test_a_partial_line_is_left_for_next_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text('{"pid": 1, "name": "a", "seconds": 1}\n{"pid": 2, "na',
                            encoding="utf-8")
            events, offset = sidecar.read_new_events(path, 0)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["pid"], 1)
            path.write_text('{"pid": 1, "name": "a", "seconds": 1}\n'
                            '{"pid": 2, "name": "b", "seconds": 2}\n', encoding="utf-8")
            events, offset = sidecar.read_new_events(path, offset)
            self.assertEqual([event["pid"] for event in events], [2])

    def test_reading_twice_does_not_repeat_an_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text('{"pid": 7, "name": "a"}\n', encoding="utf-8")
            events, offset = sidecar.read_new_events(path, 0)
            self.assertEqual(len(events), 1)
            again, _ = sidecar.read_new_events(path, offset)
            self.assertEqual(again, [])

    def test_a_missing_file_is_empty_not_an_error(self):
        events, offset = sidecar.read_new_events(Path("/nonexistent/events.jsonl"), 0)
        self.assertEqual(events, [])
        self.assertEqual(offset, 0)


class AbsenceIsNotAFailure(unittest.TestCase):
    """The whole point: no binary means the Python path, not a broken feature."""

    def test_try_start_returns_none_without_a_binary(self):
        with mock.patch.object(sidecar, "binary_path", return_value=None):
            with tempfile.TemporaryDirectory() as tmp:
                self.assertIsNone(sidecar.try_start(["antigravity"], Path(tmp) / "e.jsonl"))

    def test_try_start_returns_none_without_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(sidecar.try_start([], Path(tmp) / "e.jsonl"))

    def test_a_binary_that_cannot_start_returns_none(self):
        with tempfile.NamedTemporaryFile() as handle:
            os.chmod(handle.name, 0o644)          # not executable
            with mock.patch.object(sidecar, "binary_path", return_value=Path(handle.name)):
                with tempfile.TemporaryDirectory() as tmp:
                    self.assertIsNone(
                        sidecar.try_start(["antigravity"], Path(tmp) / "e.jsonl"))


class TheRealBinary(unittest.TestCase):
    """Runs only where the binary has been built; skipped everywhere else."""

    def test_it_writes_an_event_when_a_job_ends(self):
        if sidecar.binary_path() is None:
            self.skipTest("the sidecar has not been built on this machine")
        import subprocess
        import time
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            pattern = "sleep" if os.name != "nt" else "timeout"
            feed = sidecar.try_start([pattern], path, poll_seconds=0.2)
            self.assertIsNotNone(feed)
            try:
                time.sleep(0.6)
                if os.name == "nt":
                    job = subprocess.Popen(["cmd", "/c", "timeout", "/t", "1", "/nobreak"])
                else:
                    job = subprocess.Popen(["sleep", "0.4"])
                job.wait()
                deadline = time.time() + 5
                seen = []
                while time.time() < deadline and not seen:
                    seen = feed.poll()
                    time.sleep(0.05)
                self.assertTrue(seen, "no completion came back from the sidecar")
                self.assertIn("finished", seen[0].sentence())
            finally:
                feed.stop()

    def test_it_reports_nothing_after_being_stopped(self):
        if sidecar.binary_path() is None:
            self.skipTest("the sidecar has not been built on this machine")
        with tempfile.TemporaryDirectory() as tmp:
            feed = sidecar.try_start(["nothing-matches-this"], Path(tmp) / "e.jsonl", 0.2)
            self.assertIsNotNone(feed)
            feed.stop()
            self.assertFalse(feed.alive)
            self.assertEqual(feed.poll(), [])


if __name__ == "__main__":
    unittest.main()
