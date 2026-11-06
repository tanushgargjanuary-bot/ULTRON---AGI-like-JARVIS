"""tests/test_metacog_service.py — the metacognitive tools and skills, in the app.

`tests/test_metacog.py` tests the arithmetic. This tests the thing the assistant
actually reaches for: the tools registered in the real service, the skills that
compose them, and the workspace confinement that applies to all of it.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_jarvis.service import CustomService


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        (self.workspace / "app.py").write_text(
            "def main():\n"
            "    # TODO: remove the debug print\n"
            "    print('debug')\n"
            "    return 1\n",
            encoding="utf-8",
        )
        (self.workspace / "config.py").write_text(
            'API_KEY = "abcd1234efgh5678"\nname = "ultron"\n', encoding="utf-8")
        (self.workspace / "notes.md").write_text("# notes\nno secrets here\n",
                                                 encoding="utf-8")
        self.service = CustomService(self.base / "state", approval=lambda *_a: True)
        self.service.perform("set_workspace", {"path": str(self.workspace)})

    def tearDown(self):
        self.temp.cleanup()

    def tool(self, name, **arguments):
        return self.service.perform("tool", {"name": name, "arguments": arguments})

    def skill(self, identity, **extra):
        return self.service.perform("run_skill", {"id": identity, **extra})


class ToolsRegistered(Base):
    def test_the_nine_metacognitive_tools_are_there(self):
        names = {row["name"] for row in self.service.perform("list_tools", {})}
        for expected in ("record_prediction", "resolve_prediction", "open_predictions",
                         "calibration_report", "record_lesson", "recall_lessons",
                         "record_attempt", "choose_strategy", "self_review"):
            self.assertIn(expected, names)

    def test_the_two_workspace_tools_are_there(self):
        names = {row["name"] for row in self.service.perform("list_tools", {})}
        self.assertIn("search_text", names)
        self.assertIn("measure_code", names)


class RoundTrip(Base):
    def test_a_prediction_is_recorded_resolved_and_scored(self):
        recorded = self.tool("record_prediction", claim="the tests pass",
                            confidence=0.8, domain="ci")
        self.assertTrue(recorded["success"], recorded.get("error"))
        identifier = json.loads(recorded["output"])["id"]

        self.assertTrue(self.tool("resolve_prediction", id=identifier,
                                  outcome="correct")["success"])
        report = json.loads(self.tool("calibration_report")["output"])
        self.assertEqual(report["n"], 1)
        self.assertEqual(report["hits"], 1)
        self.assertLess(report["lower_bound"], 0.9)

    def test_the_ledger_lives_beside_the_service_state(self):
        self.tool("record_prediction", claim="x", confidence=0.5)
        self.assertTrue((self.base / "state" / "metacog.json").exists())

    def test_a_lesson_can_be_recalled(self):
        self.assertTrue(self.tool("record_lesson", trigger="running the test suite",
                                  mistake="assumed it was green",
                                  rule="run it before claiming it passes")["success"])
        rows = json.loads(self.tool("recall_lessons", task="run the tests")["output"])
        self.assertEqual(rows[0]["rule"], "run it before claiming it passes")

    def test_a_bad_outcome_is_a_clean_failure_not_a_crash(self):
        recorded = self.tool("record_prediction", claim="x", confidence=0.5)
        identifier = json.loads(recorded["output"])["id"]
        failed = self.tool("resolve_prediction", id=identifier, outcome="maybe")
        self.assertFalse(failed["success"])
        self.assertIn("correct", str(failed.get("error")))

    def test_open_predictions_lists_only_unresolved_claims(self):
        self.tool("record_prediction", claim="unresolved", confidence=0.4)
        rows = json.loads(self.tool("open_predictions")["output"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["claim"], "unresolved")


class WorkspaceTools(Base):
    def test_search_text_finds_a_planted_marker(self):
        result = self.tool("search_text", path=str(self.workspace), query="TODO")
        self.assertTrue(result["success"], result.get("error"))
        data = json.loads(result["output"])
        self.assertEqual(data["hits"][0]["file"], "app.py")
        self.assertEqual(data["hits"][0]["line"], 2)

    def test_search_text_treats_the_query_as_literal_by_default(self):
        result = self.tool("search_text", path=str(self.workspace), query="print('")
        self.assertTrue(result["success"])
        self.assertEqual(len(json.loads(result["output"])["hits"]), 1)

    def test_search_text_reports_a_bad_pattern(self):
        result = self.tool("search_text", path=str(self.workspace),
                           query="(unclosed", regex=True)
        self.assertFalse(result["success"])
        self.assertIn("compile", result["error"])

    def test_measure_code_counts_files_and_lines(self):
        data = json.loads(self.tool("measure_code", path=str(self.workspace))["output"])
        self.assertEqual(data["files"], 3)
        self.assertIn(".py", data["languages"])
        self.assertGreaterEqual(data["lines"], 7)

    def test_measure_code_is_bounded(self):
        data = json.loads(self.tool("measure_code", path=str(self.workspace),
                                    max_files=1)["output"])
        self.assertEqual(data["files"], 1)
        self.assertTrue(data["truncated"])

    def test_a_path_outside_the_workspace_is_refused(self):
        result = self.tool("search_text", path=str(self.base), query="TODO")
        self.assertFalse(result["success"])
        self.assertIn("workspace", str(result.get("error")).lower())


class Skills(Base):
    NEEDS_GIT = ("debug_context", "release_checklist")

    def test_every_new_skill_is_listed(self):
        listed = {row["id"]: row for row in self.service.perform("list_skills", {})}
        for identity in ("meta_preflight", "meta_confidence", "meta_lessons_digest",
                         "meta_strategy_brief", "meta_debrief", "code_size",
                         "biggest_files", "todo_scan", "secret_scan",
                         "test_gap_scan", "debug_context", "release_checklist",
                         "docs_freshness"):
            self.assertIn(identity, listed)

    def test_the_skills_that_need_nothing_are_applicable_in_a_plain_folder(self):
        listed = {row["id"]: row for row in self.service.perform("list_skills", {})}
        for identity, row in listed.items():
            if identity in self.NEEDS_GIT:
                continue
            if identity.startswith("meta_") or identity in (
                    "code_size", "biggest_files", "todo_scan", "secret_scan",
                    "test_gap_scan", "docs_freshness"):
                self.assertTrue(row["applicable"], f"{identity}: {row['reason']}")

    def test_a_skill_that_needs_git_says_so_instead_of_failing_later(self):
        listed = {row["id"]: row for row in self.service.perform("list_skills", {})}
        for identity in self.NEEDS_GIT:
            row = listed[identity]
            self.assertFalse(row["applicable"], identity)
            self.assertIn(".git", row["reason"])

    def test_a_meta_skill_runs_and_returns_its_steps(self):
        result = self.skill("meta_confidence")
        self.assertTrue(result["success"], result)
        steps = result.get("plan", {}).get("steps") or result.get("steps") or []
        self.assertGreaterEqual(len(steps), 2)
        for step in steps:
            self.assertTrue(step["tool_name"])
            self.assertEqual(step["status"], "completed")

    def test_a_meta_skill_works_on_an_empty_record(self):
        # The first run of a fresh install: it must answer "nothing yet" rather
        # than fail.
        result = self.skill("meta_debrief")
        self.assertTrue(result["success"], result)

    def test_todo_scan_finds_the_marker(self):
        result = self.skill("todo_scan")
        self.assertTrue(result["success"], result)
        self.assertIn("app.py", json.dumps(result))

    def test_secret_scan_finds_the_key_and_ignores_the_prose(self):
        result = self.skill("secret_scan")
        self.assertTrue(result["success"], result)
        blob = json.dumps(result)
        self.assertIn("config.py", blob)
        self.assertNotIn("notes.md", blob)

    def test_code_size_measures_the_workspace(self):
        result = self.skill("code_size")
        self.assertTrue(result["success"], result)
        self.assertIn("lines", json.dumps(result))

    def test_a_meta_skill_needs_a_workspace_like_every_other(self):
        # `select_workspace` refuses None (it needs a real directory), so the
        # engine's workspace is cleared directly — the state a fresh install is
        # in before the user picks a folder.
        self.service.control.engine.workspace = None
        with self.assertRaises(ValueError):
            self.service.perform("run_skill", {"id": "meta_confidence"})


if __name__ == "__main__":
    unittest.main()
