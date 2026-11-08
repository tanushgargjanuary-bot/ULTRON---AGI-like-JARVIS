"""Persistent issue notices and non-applying background repair jobs."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from custom_jarvis.health_center import HealthCenter


class HealthCenterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "health.json"
        self.messages = []
        self.center = HealthCenter(self.path, self.messages.append)

    def tearDown(self):
        self.temp.cleanup()

    def test_issue_persists_deduplicates_and_redacts_secrets(self):
        first = self.center.record(
            "runtime", "audio.open", "Audio failed", "api_key=ABCDEF123456", "OSError"
        )
        second = self.center.record(
            "runtime", "audio.open", "Audio failed", "api_key=ABCDEF123456", "OSError"
        )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["occurrences"], 2)
        self.assertNotIn("ABCDEF123456", self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(self.messages), 1)

        restored = HealthCenter(self.path)
        self.assertEqual(restored.issues()[0]["id"], first["id"])
        self.assertEqual(restored.issues()[0]["occurrences"], 2)

    def test_ignore_is_persistent_and_restore_makes_issue_active_again(self):
        row = self.center.record("availability", "weather", "Weather unavailable", "offline")
        self.assertTrue(self.center.ignore(row["id"]))
        self.assertEqual(self.center.issues(), [])
        self.assertEqual(HealthCenter(self.path).issues(), [])
        self.assertTrue(self.center.restore(row["id"]))
        self.assertEqual(self.center.issues()[0]["id"], row["id"])

    def test_dismissed_issue_reopens_when_detected_again(self):
        row = self.center.record("availability", "camera", "Camera unavailable", "not found")
        self.center.dismiss(row["id"])
        self.assertEqual(self.center.issues(), [])
        reopened = self.center.record("availability", "camera", "Camera unavailable", "not found")
        self.assertEqual(reopened["status"], "active")
        self.assertEqual(len(self.messages), 2)

    def test_runtime_failure_listener_records_detected_failure(self):
        from core import failures
        unsubscribe = failures.subscribe(self.center.capture_failure)
        try:
            failures.note("test.camera", "camera device is unavailable")
        finally:
            unsubscribe()
            failures.clear()
        self.assertEqual(self.center.issues()[0]["component"], "test.camera")
        self.assertIn("Detected failure", self.center.issues()[0]["summary"])

    def test_reconcile_availability_resolves_recovered_tools(self):
        self.center.reconcile_availability([("missing_action", "import error")])
        self.assertEqual(len(self.center.issues()), 1)
        self.center.reconcile_availability([])
        self.assertEqual(self.center.issues(), [])
        history = self.center.issues(include_inactive=True)
        self.assertEqual(history[0]["status"], "resolved")

    def test_local_scan_does_not_resolve_non_catalog_mcp_notices(self):
        self.center.record("mcp", "mcp", "MCP unavailable", "server down")
        self.center.reconcile_availability([])
        self.assertEqual(self.center.issues()[0]["source"], "mcp")
        self.assertEqual(self.center.issues()[0]["status"], "active")

    def test_bridge_probe_is_explicit_and_tracks_recovery(self):
        with patch("core.bridges.probe_all", return_value=[
            {"key": "example", "title": "Example", "ready": False, "detail": "not answering"},
        ]) as probe:
            self.assertEqual(self.center.scan_bridges(), 1)
        probe.assert_called_once_with()
        self.assertTrue(self.center.issues())
        with patch("core.bridges.probe_all", return_value=[
            {"key": "example", "title": "Example", "ready": True, "detail": "ready"},
        ]):
            self.assertEqual(self.center.scan_bridges(), 0)
        self.assertEqual(self.center.issues(), [])

    def test_scan_avoids_external_bridge_probes(self):
        from core.tool_catalog import Entry
        with patch("core.tool_catalog.build", return_value=[
            Entry("broken_action", "action", "other", "test", False, "import failed"),
        ]) as build:
            self.assertEqual(self.center.scan_local_catalog(), 1)
        build.assert_called_once_with(include_bridges=False)
        self.assertEqual(self.center.issues()[0]["component"], "broken_action")

    def test_fix_runs_in_background_full_rehearsal_and_never_applies(self):
        row = self.center.record("runtime", "broken_action", "Action failed", "regression")
        done = threading.Event()
        notifications = []

        class Player:
            def write_log(self, text):
                notifications.append(text)
                done.set()

        with patch("core.self_change.propose", return_value={"id": "c123"}) as propose, \
             patch("core.self_change.rehearse", return_value={
                 "ok": True, "command": "python scripts/verify.py", "full": True,
             }) as rehearse, \
             patch("core.self_change.apply") as apply:
            job = self.center.start_fix(
                row["id"], "actions/broken_action.py", "repair the reported failure",
                text="candidate source", player=Player(),
            )
            self.assertIn(job["status"], {"queued", "running"})
            self.assertTrue(done.wait(3), "background job did not notify completion")

        finished = self.center.job(job["id"])
        self.assertEqual(finished["status"], "ready_for_review")
        self.assertEqual(finished["proposal_id"], "c123")
        propose.assert_called_once()
        rehearse.assert_called_once_with("c123", full=True)
        apply.assert_not_called()
        self.assertIn("nothing was applied", notifications[0].lower())

    def test_only_one_background_self_change_runs_at_a_time(self):
        first = self.center.record("runtime", "one", "First issue", "one")
        second = self.center.record("runtime", "two", "Second issue", "two")
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        class Player:
            def write_log(self, _text):
                finished.set()

        def slow_rehearsal(_proposal_id, full=False):
            self.assertTrue(full)
            started.set()
            release.wait(3)
            return {"ok": True, "command": "verify", "full": True}

        with patch("core.self_change.propose", side_effect=[{"id": "c1"}, {"id": "c2"}]), \
             patch("core.self_change.rehearse", side_effect=slow_rehearsal):
            self.center.start_fix(first["id"], "a.py", "first", text="x", player=Player())
            self.assertTrue(started.wait(3))
            with self.assertRaisesRegex(ValueError, "already running"):
                self.center.start_fix(second["id"], "b.py", "second", text="y")
            release.set()
            self.assertTrue(finished.wait(3))
        self.assertEqual(self.center.jobs()[0]["status"], "ready_for_review")

    def test_failed_harness_never_reports_repair_ready(self):
        row = self.center.record("runtime", "bad", "Bad feature", "failed")
        done = threading.Event()

        class Player:
            def write_log(self, _text):
                done.set()

        with patch("core.self_change.propose", return_value={"id": "c456"}), \
             patch("core.self_change.rehearse", return_value={
                 "ok": False, "code": 1, "tail": "test failed", "full": True,
             }):
            job = self.center.start_fix(
                row["id"], "actions/bad.py", "fix it", text="candidate", player=Player()
            )
            self.assertTrue(done.wait(3))
        self.assertEqual(self.center.job(job["id"])["status"], "verification_failed")
        self.assertNotIn("ready for review", self.center.job(job["id"])["result"].lower())


if __name__ == "__main__":
    unittest.main()
