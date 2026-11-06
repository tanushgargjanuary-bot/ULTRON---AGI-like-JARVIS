"""The digest tells you things. It must not do things.

The standing rule for this feature is one sentence — **the digest activates
nothing** — so these tests are mostly about what must NOT happen while it builds
a report: no file written, no socket opened, no tool called, no reminder fired.

The other half holds the report itself: today's facts appear, older ones only
count, machine state (watched topics) is not presented as something the user
asked me to remember, and the spoken version stays short enough not to hold the
floor.
"""

from __future__ import annotations

import ast
import os
import socket
import subprocess
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from core import digest

ROOT = Path(__file__).resolve().parents[1]

MEMORY = {
    "notes": {
        "wifi": {"value": "1234", "updated": "2026-11-06"},
        "old": {"value": "kept from before", "updated": "2026-10-01"},
        "plain string entry": "legacy shape",          # bare string, no date
    },
    "preferences": {"lang": {"value": "English", "updated": "2026-11-06"}},
    "monitors": {"rain in Dehli": {"hash": "abc"}},     # machine state, not a fact
    "identity": {}, "projects": {}, "relationships": {}, "wishes": {},
}

NOW = datetime(2026, 11, 6, 20, 30)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.report = digest.build(now=NOW, memory=MEMORY, reminders_dir=Path("/nonexistent"))

    def test_todays_facts_are_listed(self):
        keys = {(f["category"], f["key"]) for f in self.report["remembered_today"]}
        self.assertEqual(keys, {("notes", "wifi"), ("preferences", "lang")})

    def test_older_facts_are_counted_not_listed(self):
        self.assertEqual(self.report["remembered_older"], 2)   # old + legacy string
        text = digest.render_text(self.report)
        self.assertIn("Older facts on file: 2", text)
        self.assertNotIn("kept from before", text)

    def test_watched_topics_are_not_counted_as_facts(self):
        keys = {f["key"] for f in self.report["remembered_today"]}
        self.assertNotIn("rain in Dehli", keys)

    def test_watched_topics_are_reported_separately(self):
        self.assertEqual(self.report["watching"], ["rain in Dehli"])
        self.assertIn("Watching: rain in Dehli", digest.render_text(self.report))

    def test_the_report_says_it_changed_nothing(self):
        self.assertIn("Nothing was started, sent or changed",
                      digest.render_text(self.report))

    def test_an_empty_day_still_reads_sensibly(self):
        empty = digest.build(now=NOW, memory={}, reminders_dir=Path("/nonexistent"))
        text = digest.render_text(empty)
        self.assertIn("nothing new", text.lower())
        self.assertIn("Reminders set: none", text)
        self.assertTrue(digest.render_speech(empty))

    def test_reminder_names_come_from_the_folder(self):
        import tempfile
        folder = Path(tempfile.mkdtemp())
        (folder / "dentist.py").write_text("", encoding="utf-8")
        (folder / "call_mom.py").write_text("", encoding="utf-8")
        (folder / "notes.txt").write_text("", encoding="utf-8")   # not a reminder
        report = digest.build(now=NOW, memory={}, reminders_dir=folder)
        self.assertEqual(report["reminders"], ["call_mom", "dentist"])

    def test_a_missing_reminder_folder_is_not_created(self):
        missing = Path("/tmp/definitely-not-here-digest")
        digest.build(now=NOW, memory={}, reminders_dir=missing)
        self.assertFalse(missing.exists(), "the digest must not create folders")


class InertTests(unittest.TestCase):
    """The rule: the digest activates nothing."""

    def test_building_writes_no_files(self):
        before = {p: (p.stat().st_mtime_ns, p.stat().st_size)
                  for p in (ROOT / "memory").rglob("*") if p.is_file()}
        digest.build(now=NOW, memory=MEMORY, reminders_dir=Path("/nonexistent"))
        digest.render_text(digest.build(now=NOW, memory=MEMORY))
        digest.render_speech(digest.build(now=NOW, memory=MEMORY))
        after = {p: (p.stat().st_mtime_ns, p.stat().st_size)
                 for p in (ROOT / "memory").rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_building_opens_no_socket(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network")), \
             mock.patch.object(socket, "create_connection",
                               side_effect=AssertionError("network")):
            report = digest.build(now=NOW, memory=MEMORY, reminders_dir=Path("/nonexistent"))
            self.assertTrue(digest.render_text(report))

    def test_building_starts_no_process(self):
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("process")), \
             mock.patch.object(subprocess, "Popen", side_effect=AssertionError("process")), \
             mock.patch.object(os, "system", side_effect=AssertionError("process")):
            digest.build(now=NOW, memory=MEMORY, reminders_dir=Path("/nonexistent"))

    def test_the_only_write_is_one_date(self):
        with mock.patch.object(Path, "write_text") as written, \
             mock.patch.object(Path, "mkdir"):
            digest.save_last_run("2026-11-06", path=Path("/tmp/x/state.json"))
        self.assertEqual(written.call_count, 1)
        self.assertIn("2026-11-06", written.call_args.args[0])


class SchedulerTests(unittest.TestCase):
    def test_before_the_hour_it_does_not_run(self):
        self.assertFalse(digest.should_run(datetime(2026, 11, 6, 19, 59), "20:00", ""))

    def test_after_the_hour_it_runs_once(self):
        self.assertTrue(digest.should_run(datetime(2026, 11, 6, 20, 0), "20:00", ""))
        self.assertFalse(digest.should_run(datetime(2026, 11, 6, 23, 0), "20:00", "2026-11-06"))

    def test_a_new_day_runs_again(self):
        self.assertTrue(digest.should_run(datetime(2026, 11, 7, 20, 1), "20:00", "2026-11-06"))

    def test_a_bad_hour_falls_back_to_the_default(self):
        self.assertTrue(digest.should_run(datetime(2026, 11, 6, 20, 30), "junk", ""))

    def test_last_run_round_trips(self):
        import tempfile
        path = Path(tempfile.mkdtemp()) / "state.json"
        self.assertEqual(digest.load_last_run(path), "")
        self.assertTrue(digest.save_last_run("2026-11-06", path=path))
        self.assertEqual(digest.load_last_run(path), "2026-11-06")

    def test_a_corrupt_state_file_is_not_fatal(self):
        import tempfile
        path = Path(tempfile.mkdtemp()) / "state.json"
        path.write_text("not json", encoding="utf-8")
        self.assertEqual(digest.load_last_run(path), "")


class WiringTests(unittest.TestCase):
    """The feature is only real if the app can reach it."""

    def _main_source(self) -> str:
        return (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")

    def test_main_declares_the_tool(self):
        tree = ast.parse(self._main_source())
        names = {node.value for node in ast.walk(tree)
                 if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        self.assertIn("daily_digest", names)

    def test_main_handles_it_without_a_tool_call(self):
        source = self._main_source()
        block = source.split('elif name == "daily_digest":', 1)[-1][:400]
        self.assertIn("digest_mod.build()", block)
        self.assertIn("render_text", block)

    def test_the_daily_loop_exists_and_records_the_day(self):
        source = self._main_source()
        loop = source.split("async def _digest_loop", 1)[-1][:900]
        self.assertIn("should_run", loop)
        self.assertIn("save_last_run", loop)
        self.assertIn("write_log", loop, "the digest is delivered to the log")
        self.assertNotIn("speak", loop.lower(),
                         "the digest must not speak over the user")

    def test_the_hour_is_a_readable_setting(self):
        from memory import config_manager
        self.assertRegex(config_manager.get_digest_hour(), r"^\d{2}:\d{2}$")


if __name__ == "__main__":
    unittest.main()
