"""A plan must survive a restart. These tests kill the process and start it again.

The file is the whole feature: if a plan is on disk when the app opens, one line says
so. What is not in the file matters as much as what is — no outputs, no captures, and
nothing whose name looks like a secret.
"""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from custom_jarvis import plan_state
from custom_jarvis.brain import IntentResult, IntentType
from custom_jarvis.planner import AutonomousPlanner, Plan, PlanStep, StepStatus


def _plan_dict(completed=2, total=4, goal="Tidy the downloads folder"):
    """Build a representative multi-step plan for checkpoint tests."""
    steps = []
    for number in range(total):
        steps.append(
            {
                "step_id": number + 1,
                "description": f"step {number + 1}",
                "tool_name": "read_file",
                "tool_args": {"path": f"file{number + 1}.txt"},
                "status": "completed" if number < completed else "pending",
            }
        )
    return {"goal": goal, "steps": steps, "current_step_index": completed}


class _Folder(unittest.TestCase):
    """Each test gets its own directory, so no test can see another one's plan."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.folder = Path(self._temp.name)
        self._real = plan_state.FOLDER
        plan_state.FOLDER = self.folder

    def tearDown(self):
        plan_state.FOLDER = self._real
        self._temp.cleanup()

    def written(self):
        return plan_state._path(self.folder)


class TheSavedPlan(_Folder):
    def test_a_plan_comes_back_with_its_goal_and_its_steps(self):
        self.assertTrue(plan_state.save(_plan_dict()))
        record = plan_state.load(self.folder)
        self.assertEqual(record["goal"], "Tidy the downloads folder")
        self.assertEqual(len(record["steps"]), 4)
        self.assertEqual(record["current_step_index"], 2)

    def test_the_output_of_a_step_is_not_written(self):
        plan = _plan_dict()
        plan["steps"][0]["output"] = "PRIVATE FILE CONTENTS"
        plan["steps"][0]["data"] = "PRIVATE CAPTURE"
        plan["steps"][0]["evidence"] = "PRIVATE EVIDENCE"
        plan["steps"][0]["resolved_args"] = {"content": "PRIVATE RESOLVED OUTPUT"}
        plan_state.save(plan)
        text = self.written().read_text(encoding="utf-8")
        self.assertNotIn("PRIVATE", text)

    def test_an_argument_that_names_a_secret_is_never_written(self):
        plan = _plan_dict()
        plan["steps"][1]["tool_args"] = {"api_key": "sk-live-0000"}
        self.assertFalse(plan_state.save(plan))
        self.assertFalse(self.written().exists())
        self.assertNotIn("sk-live", "".join(p.read_text(encoding="utf-8")
                                           for p in self.folder.iterdir()))

    def test_a_secret_also_removes_the_older_copy(self):
        plan_state.save(_plan_dict())
        self.assertTrue(self.written().exists())
        plan = _plan_dict()
        plan["steps"][0]["resolved_args"] = {"nested": {"password": "hunter2"}}
        self.assertFalse(plan_state.save(plan))
        self.assertFalse(self.written().exists(), "an old plan must not outlive its replacement")
        self.assertEqual(plan_state.load(self.folder), None)

    def test_a_damaged_file_is_read_as_no_file(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.written().write_text("{not json", encoding="utf-8")
        self.assertIsNone(plan_state.load(self.folder))
        self.assertIsNone(plan_state.pending(self.folder))

    def test_malformed_checkpoint_numbers_are_treated_as_absent(self):
        """Reject malformed and non-finite checkpoint indices and timestamps."""
        valid = plan_state.keep(_plan_dict())
        for field, value in (("saved", "not-a-number"),
                             ("saved", float("nan")),
                             ("current_step_index", "not-an-index"),
                             ("current_step_index", float("inf"))):
            record = dict(valid, **{field: value})
            self.written().write_text(json.dumps(record), encoding="utf-8")
            self.assertIsNone(plan_state.load(self.folder), (field, value))
            self.assertIsNone(plan_state.pending(self.folder), (field, value))
            self.assertEqual(plan_state.startup_notice(self.folder), "")

    def test_failed_replacement_invalidates_the_old_checkpoint(self):
        self.assertTrue(plan_state.save(_plan_dict(goal="old plan"), self.folder))
        with patch.object(Path, "replace", side_effect=OSError("disk full")):
            self.assertFalse(plan_state.save(_plan_dict(goal="new plan"), self.folder))
        self.assertIsNone(plan_state.load(self.folder))
        self.assertFalse(self.written().exists())

    def test_failed_update_leaves_a_sidecar_if_the_old_plan_cannot_be_deleted(self):
        """Fail closed when disk errors prevent replacing and deleting old state."""
        self.assertTrue(plan_state.save(_plan_dict(goal="old plan"), self.folder))
        original_unlink = Path.unlink

        def deny_active(path, *args, **kwargs):
            """Simulate a locked active checkpoint while allowing cleanup of temps."""
            if path.name == plan_state.NAME:
                raise PermissionError("locked")
            return original_unlink(path, *args, **kwargs)

        with (
            patch.object(Path, "replace", side_effect=OSError("disk full")),
            patch.object(Path, "unlink", new=deny_active),
        ):
            self.assertFalse(plan_state.save(_plan_dict(goal="new plan"), self.folder))
        self.assertTrue((self.folder / plan_state.INVALID_NAME).exists())
        self.assertIsNone(plan_state.load(self.folder))
        self.assertTrue(plan_state.clear(self.folder))

    def test_preview_plan_does_not_replace_or_create_the_active_checkpoint(self):
        original = _plan_dict(goal="real active plan")
        self.assertTrue(plan_state.save(original, self.folder))
        planner = AutonomousPlanner(brain=MagicMock(), tool_registry=MagicMock())
        result = planner.execute(
            "preview only",
            prepared_steps=[{"tool_name": "write_file",
                            "tool_args": {"path": "preview.txt", "content": "x"}}],
            plan_only=True,
        )
        self.assertTrue(result.success)
        record = plan_state.load(self.folder)
        self.assertEqual(record["goal"], "real active plan")

    def test_confirmation_audit_flag_survives_a_checkpoint_reload(self):
        plan = _plan_dict(completed=1)
        plan["steps"][1]["approval_recorded"] = True
        self.assertTrue(plan_state.save(plan, self.folder))
        loaded = plan_state.load(self.folder)
        self.assertTrue(loaded["steps"][1]["approval_recorded"])
        self.assertIn("confirmed earlier; will ask again", plan_state.describe(loaded))

    def test_output_reference_detection_is_recursive(self):
        self.assertTrue(plan_state.has_step_output_references(
            {"nested": ["write $STEP_1_OUTPUT", {"path": "{{prev_data}}"}]}
        ))
        self.assertFalse(plan_state.has_step_output_references(
            {"path": "notes.txt", "content": "literal text"}
        ))

    def test_nothing_is_left_behind_but_the_file_itself(self):
        plan_state.save(_plan_dict())
        self.assertEqual([p.name for p in self.folder.iterdir()], [plan_state.NAME])

    def test_clearing_twice_is_not_an_error(self):
        plan_state.save(_plan_dict())
        self.assertTrue(plan_state.clear(self.folder))
        self.assertTrue(plan_state.clear(self.folder))


class TheNotice(_Folder):
    def test_nothing_on_disk_says_nothing(self):
        self.assertEqual(plan_state.startup_notice(self.folder), "")

    def test_a_fresh_plan_is_offered_with_the_step_it_reached(self):
        plan_state.save(_plan_dict())
        notice = plan_state.startup_notice(self.folder)
        self.assertIn("step 3 of 4", notice)
        self.assertIn("resume the last plan", notice)
        self.assertIn("discard the saved plan", notice)
        self.assertIn("fresh approval", notice)
        self.assertIn("Tidy the downloads folder", notice)

    def test_an_old_plan_is_offered_and_not_applied(self):
        plan_state.save(_plan_dict())
        two_days = time.time() + 2 * 86400
        notice = plan_state.startup_notice(self.folder, now=two_days)
        self.assertIn("2d old", notice)
        self.assertIn("Not resumed automatically", notice)

    def test_pending_reports_the_age(self):
        plan_state.save(_plan_dict())
        record = plan_state.pending(self.folder, now=time.time() + 3600)
        self.assertFalse(record["stale"])
        self.assertAlmostEqual(record["age_seconds"], 3600, delta=5)

    def test_a_long_goal_is_cut_to_one_line(self):
        plan_state.save(_plan_dict(goal="x" * 400))
        notice = plan_state.startup_notice(self.folder)
        self.assertLess(len(notice), 220)


class ThePlanner(_Folder):
    """The planner writes the file itself; no caller has to remember."""

    def setUp(self):
        super().setUp()
        self.planner = AutonomousPlanner(brain=MagicMock(), verbose=False)

    def _plan(self, completed=2):
        rows = _plan_dict(completed=completed)["steps"]
        steps = [
            PlanStep(
                row["step_id"],
                row["description"],
                row["tool_name"],
                row["tool_args"],
                status=StepStatus(row["status"]),
            )
            for row in rows
        ]
        plan = Plan(
            "Tidy the downloads folder",
            IntentResult(IntentType.MULTI_STEP_PLAN, 0.9, "test"),
            steps,
        )
        plan.current_step_index = completed
        return plan

    def test_a_kill_between_step_two_and_three_leaves_two_behind(self):
        self.planner._checkpoint(self._plan(completed=2))
        record = plan_state.load(self.folder)
        done = [row for row in record["steps"] if row["status"] == "completed"]
        self.assertEqual(len(done), 2)
        self.assertEqual(record["current_step_index"], 2)
        self.assertIn("step 3 of 4", plan_state.describe(record))

    def test_a_finished_plan_leaves_no_file(self):
        plan = self._plan(completed=4)
        plan.is_completed = True
        plan_state.save(plan.to_dict())
        self.assertTrue(self.written().exists())
        self.planner._checkpoint(plan)
        self.assertFalse(self.written().exists())

    def test_a_disk_that_refuses_the_write_does_not_stop_the_plan(self):
        plan_state.FOLDER = Path(self.folder) / "\0bad"
        self.planner._checkpoint(self._plan())     # must not raise

    def test_the_saved_file_is_json_a_person_can_read(self):
        self.planner._checkpoint(self._plan())
        record = json.loads(self.written().read_text(encoding="utf-8"))
        self.assertEqual(sorted(record), ["current_step_index", "goal", "saved", "steps", "workspace"])


if __name__ == "__main__":
    unittest.main()
