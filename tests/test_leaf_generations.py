"""Generation swaps happen between sessions and retain a reversible predecessor."""

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from core.leaf_generations import LeafGenerations, _restore_modules, tree_signature


class Registry:
    def __init__(self, names=(), failures=None):
        """Prepare isolated temporary action and plugin trees for generation tests."""
        self._names = set(names)
        self._failures = dict(failures or {})

    def names(self):
        return set(self._names)

    def failures(self):
        return dict(self._failures)


class LeafGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.actions = root / "actions"
        self.plugins = root / "plugins"
        self.actions.mkdir()
        self.plugins.mkdir()
        (self.actions / "one.py").write_text("v1", encoding="utf-8")
        (self.plugins / "one.py").write_text("v1", encoding="utf-8")
        self.modules = {name: module for name, module in sys.modules.items()
                        if name.startswith(("actions.", "plugins."))}
        self.old_action_module = types.ModuleType("actions.test_leaf_generation")
        sys.modules[self.old_action_module.__name__] = self.old_action_module
        self.old = (Registry({"one"}), Registry({"plugin_one"}))
        self.manager = LeafGenerations((self.actions, self.plugins), *self.old)

    def tearDown(self):
        _restore_modules(self.modules)
        self.temp.cleanup()

    def change_source(self):
        (self.actions / "one.py").write_text("v2", encoding="utf-8")

    def test_initial_signature_failure_keeps_registries_and_retries_later(self):
        with patch("core.leaf_generations.tree_signature",
                   side_effect=[OSError("temporarily unreadable"), "readable-again"]):
            manager = LeafGenerations((self.actions, self.plugins), *self.old)
            self.assertIs(manager.active.actions, self.old[0])
            self.assertIsNone(manager.active.signature)
            self.assertIn("temporarily unreadable", manager.initial_signature_error)
            result = manager.refresh(lambda: self.old)

        self.assertTrue(result["ok"])
        self.assertTrue(result["changed"])
        self.assertEqual(manager.active.signature, "readable-again")

    def test_no_source_change_does_not_build_a_candidate(self):
        result = self.manager.refresh(lambda: self.fail("unchanged tree was rebuilt"))
        self.assertTrue(result["ok"])
        self.assertFalse(result["changed"])
        self.assertEqual(self.manager.active.number, 1)

    def test_valid_candidate_swaps_both_registries_and_keeps_previous(self):
        self.change_source()
        replacement = (Registry({"one", "two"}), Registry({"plugin_one", "plugin_two"}))
        result = self.manager.refresh(lambda: replacement)
        self.assertTrue(result["ok"])
        self.assertTrue(result["changed"])
        self.assertEqual(self.manager.active.number, 2)
        self.assertIs(self.manager.active.actions, replacement[0])
        self.assertIs(self.manager.active.plugins, replacement[1])
        self.assertIs(self.manager.previous.actions, self.old[0])

    def test_missing_active_action_refuses_candidate(self):
        self.change_source()
        result = self.manager.refresh(lambda: (Registry(), Registry({"plugin_one"})))
        self.assertFalse(result["ok"])
        self.assertIn("one", result["note"])
        self.assertIs(self.manager.active.actions, self.old[0])

    def test_missing_active_plugin_refuses_candidate(self):
        self.change_source()
        result = self.manager.refresh(lambda: (Registry({"one"}), Registry()))
        self.assertFalse(result["ok"])
        self.assertIn("plugin_one", result["note"])
        self.assertIs(self.manager.active.plugins, self.old[1])

    def test_new_discovery_failure_refuses_candidate(self):
        self.change_source()
        result = self.manager.refresh(lambda: (
            Registry({"one"}, {"new_action": "bad import"}), Registry({"plugin_one"})
        ))
        self.assertFalse(result["ok"])
        self.assertIn("new_action", result["note"])
        self.assertIs(self.manager.active.actions, self.old[0])

    def test_builder_exception_restores_the_live_module_table(self):
        self.change_source()
        old_module = self.old_action_module

        def broken_build():
            sys.modules[old_module.__name__] = types.ModuleType(old_module.__name__)
            raise RuntimeError("candidate import failed")

        result = self.manager.refresh(broken_build)
        self.assertFalse(result["ok"])
        self.assertIs(sys.modules[old_module.__name__], old_module)

    def test_rollback_restores_the_previous_generation_and_modules(self):
        self.change_source()
        new_module = types.ModuleType("actions.test_leaf_generation")
        replacement = (Registry({"one"}), Registry({"plugin_one"}))

        def build():
            sys.modules[new_module.__name__] = new_module
            return replacement

        self.assertTrue(self.manager.refresh(build)["ok"])
        self.assertIs(sys.modules[new_module.__name__], new_module)
        rollback = self.manager.rollback()
        self.assertTrue(rollback["ok"])
        self.assertEqual(self.manager.active.number, 1)
        self.assertIs(self.manager.active.actions, self.old[0])
        self.assertIs(sys.modules[new_module.__name__], self.old_action_module)

    def test_failed_rollback_does_not_replace_the_current_generation(self):
        result = self.manager.rollback()
        self.assertFalse(result["ok"])
        self.assertEqual(self.manager.active.number, 1)

    def test_underscored_helper_source_is_part_of_the_generation(self):
        helper = self.actions / "_helper.py"
        without_helper = tree_signature((self.actions, self.plugins))
        helper.write_text("v1", encoding="utf-8")
        self.assertNotEqual(without_helper, tree_signature((self.actions, self.plugins)))

        manager = LeafGenerations((self.actions, self.plugins), *self.old)
        first = manager.active.signature
        helper.write_text("v2", encoding="utf-8")
        self.assertNotEqual(first, tree_signature((self.actions, self.plugins)))
        self.assertTrue(manager.refresh(
            lambda: (Registry({"one"}), Registry({"plugin_one"}))
        )["changed"])


if __name__ == "__main__":
    unittest.main()
