"""Offline consent, anticipation and RAM-notification regression tests."""

import ast
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from actions import system_monitor
from core.insights import InsightEngine
from custom_jarvis.service import CustomService


class InsightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private" / "approved.json"
        self.now = [100.0]
        self.engine = InsightEngine(self.path, clock=lambda: self.now[0])

    def proposal(self):
        self.engine.observe("Please keep answers short.")
        row = self.engine.review()["pending"][0]
        return row, {"key": row["key"], "value": row["value"]}

    def test_observing_does_not_create_a_profile_or_directory(self):
        self.proposal()
        self.assertFalse(self.path.parent.exists())
        self.assertEqual(self.engine.review()["approved"], {})

    def test_only_approval_persists_exact_enum_preference(self):
        row, expected = self.proposal()
        self.engine.approve(row["id"], expected)
        self.assertEqual(
            json.loads(self.path.read_text()), {"response_length": "concise"}
        )
        self.assertNotIn("evidence", self.path.read_text())

    def test_approved_preference_survives_restart(self):
        row, expected = self.proposal()
        self.engine.approve(row["id"], expected)
        restored = InsightEngine(self.path)
        self.assertEqual(restored.approved["response_length"], "concise")
        self.assertIn("concise", restored.prompt_context())
        self.assertEqual(restored.review()["pending"], [])

    def test_expired_proposal_cannot_be_saved(self):
        row, expected = self.proposal()
        self.now[0] += 3601
        with self.assertRaises(ValueError):
            self.engine.approve(row["id"], expected)
        self.assertFalse(self.path.exists())

    def test_changed_proposal_cannot_be_approved_with_old_identity(self):
        row, expected = self.proposal()
        self.engine.observe("I want more detail.")
        with self.assertRaises(ValueError):
            self.engine.approve(row["id"], expected)
        self.assertFalse(self.path.exists())

    def test_tampered_expected_value_is_rejected(self):
        row, expected = self.proposal()
        with self.assertRaises(ValueError):
            self.engine.approve(
                row["id"], {"key": expected["key"], "value": "detailed"}
            )
        self.assertFalse(self.path.exists())

    def test_reject_never_saves(self):
        row, _ = self.proposal()
        self.engine.reject(row["id"])
        self.assertEqual(self.engine.review()["pending"], [])
        self.assertFalse(self.path.exists())

    def test_secret_bearing_messages_are_not_used_for_proposals(self):
        self.engine.observe("My password is SECRET; keep answers short")
        self.assertEqual(self.engine.review()["pending"], [])

    def test_does_not_infer_personality_health_or_emotion(self):
        self.engine.observe("I am anxious and tired and have a medical diagnosis.")
        self.assertEqual(self.engine.review()["pending"], [])
        self.assertFalse(self.path.exists())

    def test_currently_negated_preference_not_proposed(self):
        self.engine.observe("Do not be brief")
        self.assertEqual(self.engine.review()["pending"], [])

    def test_proposal_evidence_is_bounded(self):
        self.engine.observe("x" * 500 + " keep answers short " + "z" * 1000)
        row = self.engine.review()["pending"][0]
        self.assertLessEqual(len(row["evidence"]), 120)

    def test_readiness_is_only_a_temporary_draft_checklist(self):
        self.engine.observe("I have a presentation tomorrow.")
        view = self.engine.review()
        self.assertEqual(view["recommendations"][0]["title"], "Presentation readiness")
        self.assertEqual(len(view["recommendations"][0]["draft"]), 3)
        self.assertFalse(self.path.exists())
        self.now[0] += 3601
        self.assertEqual(self.engine.review()["recommendations"], [])

    def test_forget_clears_all_insight_state(self):
        row, expected = self.proposal()
        self.engine.approve(row["id"], expected)
        self.engine.observe("I have a meeting tomorrow")
        self.engine.forget()
        self.assertFalse(self.path.exists())
        self.assertEqual(self.engine.review()["approved"], {})
        self.assertEqual(self.engine.review()["recommendations"], [])

    def test_profile_load_ignores_unknown_keys_and_values(self):
        self.path.parent.mkdir()
        self.path.write_text(
            json.dumps(
                {
                    "personality": "obedient",
                    "tone": "professional",
                    "permissions": "all",
                    "response_length": "anything",
                }
            )
        )
        restored = InsightEngine(self.path)
        self.assertEqual(restored.approved, {"tone": "professional"})

    def test_atomic_write_failure_does_not_claim_preference_saved(self):
        row, expected = self.proposal()
        with patch("core.insights.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.engine.approve(row["id"], expected)
        self.assertEqual(self.engine.approved, {})
        self.assertFalse(self.path.exists())
        self.assertFalse(list(self.path.parent.glob(".insights-*")))

    def test_service_requires_real_approval_before_profile_write(self):
        row, _ = self.proposal()
        service = CustomService(
            Path(self.temp.name) / "service", approval=lambda *args: False
        )
        with patch("core.insights.get_insights", return_value=self.engine):
            with self.assertRaises(ValueError):
                service.perform("review_insight", {"id": row["id"]})
        self.assertFalse(self.path.exists())

    def test_service_saves_only_after_reviewed_approval(self):
        row, _ = self.proposal()
        requests = []
        service = CustomService(
            Path(self.temp.name) / "service",
            approval=lambda name, payload: requests.append((name, payload)) or True,
        )
        with patch("core.insights.get_insights", return_value=self.engine):
            result = service.perform("review_insight", {})
        self.assertEqual(requests[0][0], "save_reviewed_insight")
        self.assertEqual(requests[0][1]["value"], "concise")
        self.assertEqual(result["approved"], {"response_length": "concise"})

    def test_service_can_dismiss_next_candidate_without_saving(self):
        self.proposal()
        service = CustomService(
            Path(self.temp.name) / "service", approval=lambda *args: False
        )
        with patch("core.insights.get_insights", return_value=self.engine):
            result = service.perform("reject_insight", {})
        self.assertTrue(result["rejected"])
        self.assertEqual(self.engine.review()["pending"], [])
        self.assertFalse(self.path.exists())

    def test_automatic_session_summary_storage_is_disabled(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "main.py").read_text())
        method = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_save_session_summary"
        )
        self.assertFalse(any(isinstance(n, ast.Call) for n in ast.walk(method)))


class QuietRamTests(unittest.TestCase):
    def snapshot(self, ram=99, temp=-1):
        return (
            patch.object(system_monitor.psutil, "cpu_percent", return_value=0),
            patch.object(
                system_monitor.psutil,
                "virtual_memory",
                return_value=SimpleNamespace(
                    percent=ram, used=8 * 1024**3, total=16 * 1024**3
                ),
            ),
            patch.object(system_monitor, "_get_cpu_temp", return_value=temp),
            patch.object(system_monitor, "_get_gpu_usage", return_value=-1),
        )

    def test_high_ram_never_generates_default_alert(self):
        a, b, c, d = self.snapshot()
        with a, b, c, d:
            monitor = system_monitor.SystemMonitor()
            for _ in range(5):
                self.assertIsNone(monitor.check())
            self.assertNotIn("ram", monitor._last_alert)

    def test_other_temperature_alerts_are_not_removed(self):
        a, b, c, d = self.snapshot(temp=99)
        with a, b, c, d:
            result = system_monitor.SystemMonitor().check()
        self.assertIn("temperature", result)
        self.assertNotIn("RAM", result)

    def test_explicit_system_status_still_includes_ram(self):
        a, b, c, d = self.snapshot()
        with a, b, c, d:
            result = system_monitor.get_system_status()
        self.assertEqual(result["ram_percent"], 99)
        self.assertEqual(result["ram_total_gb"], 16)

    def test_proactive_prompt_forbids_ram_nags(self):
        from actions.proactive import ProactiveEngine

        prompt = ProactiveEngine().build_prompt({})
        self.assertIn("Never give unsolicited RAM", prompt)


if __name__ == "__main__":
    unittest.main()
