"""The leaf loaders can build fresh registries without touching core modules."""

import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path

from core.action_loader import discover_actions
from core.plugin_loader import discover_plugins
from core.leaf_generations import _restore_modules, clear_leaf_modules


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

    def test_forced_clear_removes_stale_parent_package_attribute(self):
        package = importlib.import_module("actions")
        name = "actions._arena_reload_probe"
        module = types.ModuleType(name)
        sys.modules[name] = module
        package._arena_reload_probe = module

        clear_leaf_modules("actions", force_reload=True)

        self.assertNotIn(name, sys.modules)
        self.assertNotIn("_arena_reload_probe", package.__dict__)

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

    def test_action_reload_keeps_sibling_imports_on_one_generation(self):
        package = importlib.import_module("actions")
        dependency = self.actions / "a_dependency.py"
        consumer = self.actions / "z_consumer.py"

        def dependency_source(value):
            return f"VALUE = '{value}'\n"

        consumer.write_text(
            "import actions.a_dependency as dependency\n"
            "def run(parameters=None, **kwargs): return dependency.VALUE\n"
            "TOOL = {'name': 'generation_consumer', 'description': 'test', "
            "'parameters': {'type': 'OBJECT', 'properties': {}}, 'handler': run}\n",
            encoding="utf-8",
        )
        dependency.write_text(dependency_source("old"), encoding="utf-8")
        old = discover_actions(self.actions, logger=lambda _line: None)
        self.assertEqual(old.run("generation_consumer", {}, {}), "old")

        dependency.write_text(dependency_source("new"), encoding="utf-8")
        new = discover_actions(self.actions, logger=lambda _line: None, force_reload=True)
        dependency_module = sys.modules["actions.a_dependency"]
        consumer_module = sys.modules["actions.z_consumer"]
        self.assertEqual(new.run("generation_consumer", {}, {}), "new")
        self.assertIs(consumer_module.dependency, dependency_module)
        self.assertIs(package.a_dependency, dependency_module)

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

    def test_forced_leaf_discovery_preserves_referee_policy_identity(self):
        policy = importlib.import_module("core.policy")
        tier_type = policy.Tier

        discover_actions(self.actions, logger=lambda _line: None, force_reload=True)
        discover_plugins(self.plugins, set(), logger=lambda _line: None,
                         force_reload=True)

        self.assertIs(sys.modules["core.policy"], policy)
        self.assertIs(policy.Tier, tier_type)


if __name__ == "__main__":
    unittest.main()
