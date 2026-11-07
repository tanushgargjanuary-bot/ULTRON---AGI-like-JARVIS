"""tests/test_undo_semantic.py — Unit tests for flexible semantic undo and rollback dispatch.

Verifies:
1. Tool descriptions and prompt cues do not constrain the LLM to literal strings.
2. Broad semantic reversal intentions (rollback, discard, mistake, cancel, put it back, etc.)
   resolve to revert.
3. Self-modifications and hot-plugin deployments automatically push reversible closures
   onto the shared core.undo stack.
4. Calling general undo_last() rolls back modifications and restores previous state.
5. Thread-safety, removal matching, and error isolation of the undo stack.
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from actions import self_change as self_change_tool
from core import self_change, undo
from actions import file_controller as fc


APP_CODE = "def greeting():\n    return 'hello'\n"
NEW_APP_CODE = "def greeting():\n    return 'hello, ultron'\n"
PLUGIN_CODE = "PLUGIN = {'name': 'sample_test', 'description': 'test'}\ndef run(p):\n    return 'ok'\n"


class WithFakeProject(unittest.TestCase):
    def setUp(self):
        undo.clear()
        self._temp = tempfile.TemporaryDirectory()
        self.project = Path(self._temp.name) / "project"
        self.project.mkdir()
        (self.project / "app.py").write_text(APP_CODE, encoding="utf-8")
        (self.project / "plugins").mkdir(parents=True, exist_ok=True)
        for protected in self_change.PROTECTED:
            path = self.project / protected
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("PROTECTED = True\n", encoding="utf-8")
        self_change.set_root(self.project)
        self_change.set_store(Path(self._temp.name) / "store")

    def tearDown(self):
        self_change.set_root(None)
        self_change.set_store(None)
        self._temp.cleanup()
        undo.clear()

    def read(self, name: str) -> str:
        return (self.project / name).read_text(encoding="utf-8")

    def stage_and_confirm(self, path="app.py", find="'hello'", replace="'hello, ultron'") -> str:
        proposal = self_change.propose(
            path, "test semantic change",
            find=find, replace=replace
        )
        pid = proposal["id"]
        self_change.rehearse(pid)
        self_change.confirm(pid, "voice")
        self_change.confirm(pid, "panel")
        return pid


class TestSemanticActionResolution(WithFakeProject):
    """Ensure LLM reversal actions are never constrained to literal keywords."""

    def test_reversal_synonyms_resolve_to_revert(self):
        # Test diverse synonym actions
        synonyms = [
            "rollback", "roll_back", "discard", "cancel", "mistake",
            "restore", "undo", "put_back", "take_back", "unapply"
        ]
        for syn in synonyms:
            # Reset app.py to base content
            (self.project / "app.py").write_text(APP_CODE, encoding="utf-8")
            # Stage & apply a fresh change to test this synonym
            p = self.stage_and_confirm(replace=f"'{syn}'")
            self_change_tool.self_modify({"action": "apply", "change": p})
            self.assertIn(syn, self.read("app.py"))

            # Calling self_modify with the synonym action must revert it
            result = self_change_tool.self_modify({"action": syn, "change": p})
            self.assertIn("Put back", result)
            self.assertNotIn(syn, self.read("app.py"))

    def test_conversational_phrasings_resolve_to_revert(self):
        phrasings = [
            "cancel the last edit",
            "that was a mistake",
            "go back to previous state",
            "put it back",
            "discard that change",
        ]
        for phrase in phrasings:
            # Reset app.py to base content
            (self.project / "app.py").write_text(APP_CODE, encoding="utf-8")
            p = self.stage_and_confirm(replace=f"'{phrase[:6]}'")
            self_change_tool.self_modify({"action": "apply", "change": p})
            result = self_change_tool.self_modify({"action": phrase, "change": p})
            self.assertIn("Put back", result)

    def test_unknown_action_still_reported_cleanly(self):
        res = self_change_tool.self_modify({"action": "levitate"})
        self.assertIn("I do not know the action 'levitate'", res)
        self.assertIn("revert", res)


class TestReversibleClosures(WithFakeProject):
    """Ensure self-modifications and plugins automatically push undo closures."""

    def test_self_modification_pushes_undo_and_rolls_back_via_general_undo(self):
        pid = self.stage_and_confirm()
        res = self_change_tool.self_modify({"action": "apply", "change": pid})
        self.assertIn("Applied", res)
        self.assertEqual(self.read("app.py"), NEW_APP_CODE)

        # Undo stack must hold the change
        self.assertTrue(undo.can_undo())
        self.assertIn("self-modification to app.py", undo.peek())

        # General undo_last() (triggered by voice 'undo' tool) must roll it back
        undone_msg = undo.undo_last()
        self.assertIn("Undone: self-modification to app.py", undone_msg)
        self.assertEqual(self.read("app.py"), APP_CODE)

    def test_plugin_deployment_via_self_change_pushes_plugin_label(self):
        plugin_rel = "plugins/hello_tool.py"
        proposal = self_change.propose(
            plugin_rel, "add plugin",
            new_text=PLUGIN_CODE
        )
        pid = proposal["id"]
        self_change.rehearse(pid)
        self_change.confirm(pid, "voice")
        self_change.confirm(pid, "panel")

        self_change_tool.self_modify({"action": "apply", "change": pid})
        self.assertTrue((self.project / plugin_rel).exists())
        self.assertIn("deployed plugin hello_tool.py", undo.peek())

        # Rolling back via general undo
        undone = undo.undo_last()
        self.assertIn("Undone: deployed plugin hello_tool.py", undone)

    def test_revert_without_explicit_id_reverts_latest_applied(self):
        pid = self.stage_and_confirm()
        self_change_tool.self_modify({"action": "apply", "change": pid})
        self.assertEqual(self.read("app.py"), NEW_APP_CODE)

        # Call revert with no change/proposal parameter
        res = self_change_tool.self_modify({"action": "revert"})
        self.assertIn("Put back: app.py", res)
        self.assertEqual(self.read("app.py"), APP_CODE)

    def test_revert_removes_entry_from_undo_stack(self):
        pid = self.stage_and_confirm()
        self_change_tool.self_modify({"action": "apply", "change": pid})
        self.assertTrue(undo.can_undo())

        # When explicitly reverted through tool, the undo stack shouldn't retain redundant entry
        self_change_tool.self_modify({"action": "revert", "change": pid})
        self.assertFalse(undo.can_undo())

    def test_file_controller_creates_plugin_with_deployed_label(self):
        plugin_file = self.project / "plugins" / "custom_hot.py"
        fc.create_file(str(plugin_file), content=PLUGIN_CODE)
        self.assertTrue(plugin_file.exists())
        self.assertEqual(undo.peek(), "deployed plugin custom_hot.py")

        # Roll back via general undo
        undo.undo_last()
        self.assertFalse(plugin_file.exists())

    def test_file_controller_writes_plugin_with_deployed_label(self):
        plugin_file = self.project / "plugins" / "custom_hot2.py"
        plugin_file.write_text("ORIGINAL = 1\n", encoding="utf-8")

        fc.write_file(str(plugin_file), content=PLUGIN_CODE)
        self.assertEqual(undo.peek(), "deployed plugin custom_hot2.py")
        self.assertEqual(plugin_file.read_text(encoding="utf-8"), PLUGIN_CODE)

        # Roll back via general undo
        undo.undo_last()
        self.assertEqual(plugin_file.read_text(encoding="utf-8"), "ORIGINAL = 1\n")


class TestUndoStackRobustness(unittest.TestCase):
    def setUp(self):
        undo.clear()

    def tearDown(self):
        undo.clear()

    def test_multithreaded_push_and_undo_safety(self):
        errors = []

        def worker(idx):
            try:
                for i in range(15):
                    state = [i]
                    def make_undo(s=state):
                        s[0] -= 1
                        return "ok"
                    undo.push_undo(f"w{idx}_{i}", make_undo)
                    if i % 2 == 0:
                        undo.undo_last()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)

    def test_undo_matching_and_remove_matching(self):
        undo.push_undo("item 1", lambda: "1", metadata={"tag": "first"})
        undo.push_undo("item 2", lambda: "2", metadata={"tag": "target"})
        undo.push_undo("item 3", lambda: "3", metadata={"tag": "third"})

        # Target item 2 specifically
        res = undo.undo_matching(lambda e: e.metadata.get("tag") == "target")
        self.assertIn("Undone: item 2", res)

        # History should now contain only item 3 and item 1
        hist = undo.history()
        self.assertEqual(hist, ["item 3", "item 1"])

        # Remove matching
        removed = undo.remove_matching(lambda e: e.metadata.get("tag") == "first")
        self.assertTrue(removed)
        self.assertEqual(undo.history(), ["item 3"])

    def test_failing_closure_isolated_without_crash(self):
        def broken():
            raise RuntimeError("simulated rollback hardware error")

        undo.push_undo("risky op", broken)
        result = undo.undo_last()
        self.assertIn("Could not undo 'risky op'", result)
        self.assertIn("simulated rollback hardware error", result)
        # Stack should be popped and clean
        self.assertFalse(undo.can_undo())


if __name__ == "__main__":
    unittest.main()
