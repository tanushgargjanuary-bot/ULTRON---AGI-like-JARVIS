"""The leaf loaders can build fresh registries without touching core modules."""

import sys
import tempfile
import unittest
from pathlib import Path

from core.action_loader import discover_actions
from core.plugin_loader import discover_plugins
from core.leaf_generations import _restore_modules


class LeafReloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.actions = root / "actions"
        self.plugins = root / "plugins"
        self.actions.mkdir()
        self.plugins.mkdir()
        self.saved = {name: module for name, module in sys.modules.items()
                      if name.startswith(("actions.", "plugins."))}

    def tearDown(self):
        _restore_modules(self.saved)
        self.temp.cleanup()

    def test_action_generation_uses_new_handler_source(self):
        action = self.actions / "reloadable.py"
        action.write_text(
            "def run(parameters=None, **kwargs): return 'one'\n"
            "TOOL = {'name': 'reloadable_action', 'description': 'test', "
            "'parameters': {'type': 'OBJECT', 'properties': {}}, 'handler': run}\n",
            encoding="utf-8",
        )
        old = discover_actions(self.actions, logger=lambda _line: None)
        self.assertEqual(old.run("reloadable_action", {}, {}), "one")
        action.write_text(
            "def run(parameters=None, **kwargs): return 'two'\n"
            "TOOL = {'name': 'reloadable_action', 'description': 'test', "
            "'parameters': {'type': 'OBJECT', 'properties': {}}, 'handler': run}\n",
            encoding="utf-8",
        )
        new = discover_actions(self.actions, logger=lambda _line: None, force_reload=True)
        self.assertEqual(new.run("reloadable_action", {}, {}), "two")
        self.assertEqual(old.run("reloadable_action", {}, {}), "one")

    def test_plugin_generation_uses_new_run_function(self):
        plugin = self.plugins / "reloadable.py"

        def source(answer):
            return ("PLUGIN = {'name': 'reloadable_plugin', 'description': 'test', "
                    "'parameters': {'type': 'OBJECT', 'properties': {}}}\n"
                    f"def run(parameters=None): return '{answer}'\n")

        plugin.write_text(source("one"), encoding="utf-8")
        old = discover_plugins(self.plugins, set(), logger=lambda _line: None)
        self.assertEqual(old.names(), {"reloadable_plugin"})
        plugin.write_text(source("two"), encoding="utf-8")
        new = discover_plugins(self.plugins, set(), logger=lambda _line: None,
                               force_reload=True)
        self.assertEqual(new.names(), {"reloadable_plugin"})
        self.assertEqual(old.run("reloadable_plugin", {}, player=None,
                                 session_memory=None), "one")
        self.assertEqual(new.run("reloadable_plugin", {}, player=None,
                                 session_memory=None), "two")

    def test_a_referee_module_is_not_part_of_leaf_reload(self):
        # The loader knows only the two explicit leaf packages.
        self.assertFalse(any(name.startswith("core.policy.")
                             for name in self.saved))


if __name__ == "__main__":
    unittest.main()
