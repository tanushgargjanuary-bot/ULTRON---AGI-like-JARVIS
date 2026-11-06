"""Offline tests of actual MARK confirmation dispatch and the custom service."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from core import confirm, custom_gate
from custom_jarvis.service import CustomService
from plugins import custom_jarvis as plugin



# ── the config file is the user's, not the test's ────────────────────────────
#
# Building a real MainWindow saves the window size, and saving it goes to the
# real config/api_keys.json. Measured: running this module wrote
# {"window_size": [1600, 900]} into the project's own config, so running the
# verification on the owner's machine would have changed the size their window
# reopens at. The config is pointed at a temporary directory for the whole
# module; every assertion below is unchanged.
_TEMP_CONFIG = None
_SAVED_PATHS = None


def setUpModule():
    global _TEMP_CONFIG, _SAVED_PATHS
    try:
        from memory import config_manager as _cm
    except Exception:                     # pragma: no cover - no Qt environment
        return
    _TEMP_CONFIG = tempfile.TemporaryDirectory()
    _SAVED_PATHS = (_cm.CONFIG_DIR, _cm.CONFIG_FILE)
    _cm.CONFIG_DIR = Path(_TEMP_CONFIG.name)
    _cm.CONFIG_FILE = Path(_TEMP_CONFIG.name) / "api_keys.json"


def tearDownModule():
    try:
        from memory import config_manager as _cm
    except Exception:                     # pragma: no cover
        return
    if _SAVED_PATHS is not None:
        _cm.CONFIG_DIR, _cm.CONFIG_FILE = _SAVED_PATHS
    if _TEMP_CONFIG is not None:
        _TEMP_CONFIG.cleanup()

class GateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        confirm.resolve(False)
        confirm.bind(MagicMock(), MagicMock())
        self.player = MagicMock()
        self.handler = AsyncMock(
            return_value=SimpleNamespace(response={"result": "actual result"})
        )
        self.fc = SimpleNamespace(
            name="some_unknown_plugin", id="one", args={"content": "original"}
        )

    def tearDown(self):
        confirm.resolve(False)
        confirm.bind(None, None)

    async def test_unknown_action_waits_for_human(self):
        result = await custom_gate.dispatch(
            self.fc, self.handler, self.player, SimpleNamespace
        )
        self.assertIn("CONFIRMATION_PENDING", result.response["result"])
        self.handler.assert_not_awaited()

    async def test_human_cancel_does_not_dispatch(self):
        await custom_gate.dispatch(self.fc, self.handler, self.player, SimpleNamespace)
        confirm.resolve(False)
        await asyncio.sleep(0.01)
        self.handler.assert_not_awaited()

    async def test_human_confirm_dispatches_frozen_arguments_once(self):
        await custom_gate.dispatch(self.fc, self.handler, self.player, SimpleNamespace)
        self.fc.args["content"] = "changed after approval was shown"
        confirm.resolve(True)
        for _ in range(100):
            if self.handler.await_count:
                break
            await asyncio.sleep(0.01)
        self.handler.assert_awaited_once()
        self.assertEqual(self.handler.call_args.args[0].args["content"], "original")
        confirm.resolve(True)
        await asyncio.sleep(0.01)
        self.handler.assert_awaited_once()

    async def test_missing_ui_fails_closed(self):
        confirm.bind(None, None)
        result = await custom_gate.dispatch(
            self.fc, self.handler, None, SimpleNamespace
        )
        self.assertIn("not available", result.response["result"])
        self.handler.assert_not_awaited()

    async def test_read_only_tool_is_immediate(self):
        self.fc.name = "system_status"
        await custom_gate.dispatch(self.fc, self.handler, self.player, SimpleNamespace)
        self.handler.assert_awaited_once()
        self.assertEqual(confirm.pending_title(), "")

    async def test_model_confirmed_parameter_cannot_approve(self):
        self.fc.args = {"confirmed": "yes", "approved": True}
        await custom_gate.dispatch(self.fc, self.handler, self.player, SimpleNamespace)
        self.handler.assert_not_awaited()

    async def test_existing_pending_confirmation_not_replaced(self):
        confirm.request("first", "First action", "detail", lambda: "done")
        result = await custom_gate.dispatch(
            self.fc, self.handler, self.player, SimpleNamespace
        )
        self.assertIn("Another confirmation", result.response["result"])
        self.assertEqual(confirm.pending_title(), "First action")
        self.handler.assert_not_awaited()

    async def test_custom_service_owns_its_per_step_gate(self):
        self.fc.name = "custom_jarvis"
        await custom_gate.dispatch(self.fc, self.handler, self.player, SimpleNamespace)
        self.handler.assert_awaited_once()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "project"
        self.workspace.mkdir()
        (self.workspace / "note.txt").write_text("before", encoding="utf-8")
        self.approved = True
        self.approvals = []

        def approve(name, args):
            self.approvals.append(name)
            return self.approved

        self.service = CustomService(self.base / "state", approval=approve)
        self.service.perform("set_workspace", {"path": str(self.workspace)})
        self.approvals.clear()

    def tool(self, name, **args):
        return self.service.perform("tool", {"name": name, "arguments": args})

    def test_every_skill_is_listed_and_applicable_in_a_workspace(self):
        skills = self.service.perform("list_skills", {})
        self.assertGreaterEqual(len(skills), 24)
        ids = [row["id"] for row in skills]
        self.assertEqual(len(ids), len(set(ids)))
        for row in skills:
            self.assertTrue(row["title"], row["id"])
            self.assertIn("applicable", row)
        # The meta-cognitive family is reachable through the real plugin path.
        self.assertTrue(any(row["id"].startswith("meta_") for row in skills))

    def test_read_only_operation_needs_no_write_approval(self):
        self.assertTrue(self.tool("read_file", path="note.txt")["success"])
        self.assertEqual(self.approvals, [])

    def test_write_has_one_real_approval_and_readback_verification(self):
        result = self.tool("write_file", path="note.txt", content="after")
        self.assertTrue(result["success"])
        self.assertEqual(result["metadata"]["verification"], "verified")
        self.assertTrue(result["metadata"]["backup_id"])
        self.assertEqual(self.approvals, ["write_file"])

    def test_denied_write_preserves_file(self):
        self.approved = False
        result = self.tool("write_file", path="note.txt", content="after")
        self.assertFalse(result["success"])
        self.assertEqual((self.workspace / "note.txt").read_text(), "before")

    def test_traversal_is_blocked_before_raw_dispatch(self):
        with patch.object(self.service.control.engine.registry, "execute") as raw:
            result = self.tool("write_file", path="../outside.txt", content="bad")
        self.assertFalse(result["success"])
        raw.assert_not_called()

    def test_failure_fingerprint_capture_uses_real_metadata(self):
        result = self.tool("read_file", path=" missing.txt")
        self.assertFalse(result["success"])
        self.assertIsNotNone(self.service.incident)
        self.assertTrue(self.service.incident.fingerprint)
        self.assertIsNotNone(
            self.service.store.get_fingerprint(self.service.incident.fingerprint)
        )

    def test_goal_assertions_verify_actual_artifact(self):
        result = self.service.perform(
            "verify_goal",
            {"assertions": [{"kind": "file_exists", "target": "note.txt"}]},
        )
        self.assertTrue(result["goal_verified"])

    def test_transaction_rollback_uses_approval_gate(self):
        self.tool("write_file", path="note.txt", content="after")
        transaction = self.service.control.engine.transaction_id
        result = self.service.perform(
            "rollback_transaction", {"transaction_id": transaction}
        )
        self.assertTrue(result["success"])
        self.assertEqual((self.workspace / "note.txt").read_text(), "before")
        self.assertIn("rollback_transaction", self.approvals)

    def test_preview_skill_does_not_execute_tools(self):
        skill = self.service.perform("list_skills", {})[0]["id"]
        with patch.object(self.service.control, "execute") as execute:
            self.service.perform("preview_skill", {"id": skill})
        execute.assert_not_called()

    def test_workspace_setting_persists_separately_from_mark_config(self):
        state = json.loads((self.base / "state" / "workspace.json").read_text())
        # The service stores a resolved path. On Windows the fixture's temp
        # folder arrives in 8.3 short form (RUNNER~1), so the comparison has to
        # resolve both sides or it compares two spellings of one folder.
        self.assertEqual(Path(state["path"]).resolve(), Path(self.workspace).resolve())
        second = CustomService(self.base / "state", approval=lambda *args: False)
        self.assertEqual(second.control.engine.workspace, self.workspace)

    def test_no_ui_means_no_custom_mutation(self):
        service = CustomService(self.base / "headless")
        with self.assertRaises(ValueError):
            service.perform("set_workspace", {"path": str(self.workspace)})

    def test_malformed_plugin_payload_does_not_create_service(self):
        with patch("custom_jarvis.service.get_service") as get:
            result = plugin.run({"operation": "tool", "payload_json": "[]"})
        self.assertIn("rejected", result)
        get.assert_not_called()

    def test_worker_start_is_not_reported_as_completion(self):
        player = MagicMock()
        started = self.service.submit("list_skills", {}, player)
        self.assertEqual(started["state"], "started")
        self.assertIn("Not completion", started["note"])
        # Wait by acquiring the job mutex, not by spawning another task.
        self.assertTrue(self.service.busy.acquire(timeout=5))
        self.service.busy.release()
        self.assertEqual(len(self.service.last_result), len(self.service.perform("list_skills", {})))
        player.show_content.assert_called()

    def test_repair_test_does_not_promote_and_rollback_is_tracked(self):
        source = 'def adapt(args): return dict(args, path=args["path"].strip())\n'
        result = self.service.perform(
            "repair_test",
            {
                "tool": "read_file",
                "source": source,
                "contracts": [
                    {"input": {"path": " note.txt"}, "expected": {"path": "note.txt"}}
                ],
            },
        )
        self.assertFalse(result["activated"])
        self.assertIsNone(self.service.repairs.current("read_file"))
        self.service.perform("repair_activate", {})
        context = self.service.repairs.context_key("read_file")
        self.service.perform("repair_rollback", {"tool": "read_file"})
        self.assertEqual(
            len(self.service.breaker.states[("read_file", context)]["rollback_events"]),
            1,
        )

    def test_stop_blocks_following_tools(self):
        self.service.submit("stop", {})
        result = self.tool("write_file", path="note.txt", content="bad")
        self.assertFalse(result["success"])
        self.assertEqual(result["metadata"]["error_code"], "CANCELLED")


class NativeHudTests(unittest.TestCase):
    def test_original_mark_window_has_custom_controls(self):
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt6.QtWidgets import QApplication

            import ui
        except ImportError as exc:
            self.skipTest(str(exc))
        app = QApplication.instance() or QApplication([])
        window = ui.MainWindow(
            str(Path(__file__).resolve().parents[1] / "core" / "face_model.obj")
        )
        try:
            self.assertEqual(
                window._custom_workspace_btn.text(), "CUSTOM: SELECT WORKSPACE"
            )
            self.assertEqual(
                window._custom_skills_btn.text(), "CUSTOM: WORKSPACE SKILLS"
            )
            self.assertEqual(
                window._custom_status_btn.text(), "CUSTOM: STATUS / EVIDENCE"
            )
            self.assertEqual(window._custom_stop_btn.text(), "CUSTOM: STOP TASK")
            self.assertEqual(
                window._custom_insights_btn.text(), "CUSTOM: INSIGHTS / NEXT STEPS"
            )
            app.processEvents()
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
