"""
Tests for Hot-Plugin Forge architecture:
- PluginRegistry.reload_or_register and unregister in core/plugin_loader.py
- actions/plugin_forge.py validation, rehearsal, hot-loading, policy, undo, and UI dispatch.
"""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from actions.plugin_forge import (
    forge_plugin,
    rehearse_in_sandbox,
    validate_plugin_ast,
)
from core import policy, undo
from core.plugin_loader import (
    discover_plugins,
    get_active_registry,
    PluginRecord,
    PluginRegistry,
)


class PluginRegistryReloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.plugins_dir = Path(self.tmp_dir.name)
        self.registry = discover_plugins(
            self.plugins_dir,
            core_tool_names={"system_status", "web_search"},
            logger=lambda _m: None,
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_reload_or_register_new_plugin(self):
        plugin_file = self.plugins_dir / "dice_roll.py"
        plugin_file.write_text(
            '''"""Dice roll plugin."""
PLUGIN = {
    "name": "dice_roll",
    "description": "Rolls a dice and returns result.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    return "Rolled a 6."
''',
            encoding="utf-8",
        )

        rec = self.registry.reload_or_register(plugin_file)
        self.assertTrue(rec.valid)
        self.assertEqual(rec.name, "dice_roll")
        self.assertTrue(self.registry.has("dice_roll"))

        # Verify tool declaration is available
        decls = [d["name"] for d in self.registry.get_tool_declarations()]
        self.assertIn("dice_roll", decls)

        # Verify it can be executed immediately
        res = self.registry.run("dice_roll", {})
        self.assertEqual(res, "Rolled a 6.")

    def test_reload_or_register_updates_existing_plugin(self):
        plugin_file = self.plugins_dir / "counter.py"
        plugin_file.write_text(
            '''PLUGIN = {
    "name": "counter",
    "description": "Returns version 1.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
def run(parameters: dict, player=None) -> str:
    return "v1"
''',
            encoding="utf-8",
        )
        rec1 = self.registry.reload_or_register(plugin_file)
        self.assertTrue(rec1.valid)
        self.assertEqual(self.registry.run("counter", {}), "v1")

        # Update the file to v2
        plugin_file.write_text(
            '''PLUGIN = {
    "name": "counter",
    "description": "Returns version 2.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
def run(parameters: dict, player=None) -> str:
    return "v2"
''',
            encoding="utf-8",
        )
        rec2 = self.registry.reload_or_register(plugin_file)
        self.assertTrue(rec2.valid)
        self.assertEqual(self.registry.run("counter", {}), "v2")

    def test_reload_or_register_collision_with_core_tool(self):
        plugin_file = self.plugins_dir / "web_search.py"
        plugin_file.write_text(
            '''PLUGIN = {
    "name": "web_search",
    "description": "Collides with core.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
def run(parameters: dict) -> str:
    return "boom"
''',
            encoding="utf-8",
        )
        rec = self.registry.reload_or_register(plugin_file)
        self.assertFalse(rec.valid)
        self.assertIn("collides with a core tool", rec.error)
        self.assertFalse(self.registry.has("web_search"))

    def test_reload_or_register_invalid_syntax(self):
        plugin_file = self.plugins_dir / "syntax_err.py"
        plugin_file.write_text("def broken(: pass", encoding="utf-8")
        rec = self.registry.reload_or_register(plugin_file)
        self.assertFalse(rec.valid)
        self.assertFalse(self.registry.has("syntax_err"))

    def test_unregister(self):
        plugin_file = self.plugins_dir / "temporary.py"
        plugin_file.write_text(
            '''PLUGIN = {
    "name": "temporary",
    "description": "Temporary tool.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
def run(parameters: dict) -> str:
    return "temp"
''',
            encoding="utf-8",
        )
        self.registry.reload_or_register(plugin_file)
        self.assertTrue(self.registry.has("temporary"))

        unregistered = self.registry.unregister("temporary")
        self.assertTrue(unregistered)
        self.assertFalse(self.registry.has("temporary"))

    def test_thread_safe_concurrent_reloads(self):
        """Verify concurrent operations across threads do not race or raise."""
        errors = []

        def worker(idx: int):
            try:
                pfile = self.plugins_dir / f"worker_{idx}.py"
                pfile.write_text(
                    f'''PLUGIN = {{
    "name": "worker_{idx}",
    "description": "Worker plugin {idx}.",
    "parameters": {{"type": "OBJECT", "properties": {{}}}},
}}
def run(parameters: dict) -> str:
    return "ok_{idx}"
''',
                    encoding="utf-8",
                )
                rec = self.registry.reload_or_register(pfile)
                if not rec.valid:
                    errors.append(f"Worker {idx} failed to validate: {rec.error}")
                out = self.registry.run(f"worker_{idx}", {})
                if out != f"ok_{idx}":
                    errors.append(f"Worker {idx} returned {out}")
            except Exception as e:
                errors.append(f"Exception in worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


class PluginForgeActionTests(unittest.TestCase):
    def setUp(self):
        undo.clear()

    def tearDown(self):
        undo.clear()

    def test_validate_plugin_ast(self):
        good_code = '''
PLUGIN = {
    "name": "valid_tool",
    "description": "Valid tool description.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
def run(parameters: dict, player=None) -> str:
    return "ok"
'''
        ok, err = validate_plugin_ast(good_code, "valid_tool")
        self.assertTrue(ok, err)

        bad_syntax = "def broken(:"
        ok, err = validate_plugin_ast(bad_syntax, "broken")
        self.assertFalse(ok)
        self.assertIn("Syntax error", err)

        missing_plugin = "def run(parameters): return 'ok'"
        ok, err = validate_plugin_ast(missing_plugin, "no_plugin")
        self.assertFalse(ok)
        self.assertIn("PLUGIN", err)

        missing_run = 'PLUGIN = {"name": "x"}'
        ok, err = validate_plugin_ast(missing_run, "x")
        self.assertFalse(ok)
        self.assertIn("def run", err)

    def test_rehearse_in_sandbox(self):
        valid_code = '''
PLUGIN = {
    "name": "rehearsal_test",
    "description": "Rehearsal test description.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
def run(parameters: dict, player=None, session_memory=None) -> str:
    return "rehearsal passed"
'''
        ok, msg = rehearse_in_sandbox("rehearsal_test", valid_code)
        self.assertTrue(ok, msg)

        failing_code = '''
PLUGIN = {
    "name": "exploder",
    "description": "Explodes on run.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
def run(parameters: dict, player=None) -> str:
    raise RuntimeError("Sandbox should catch this explosion")
'''
        ok, msg = rehearse_in_sandbox("exploder", failing_code)
        self.assertFalse(ok)
        self.assertIn("Sandbox execution check failed", msg)

    def test_forge_and_undo_lifecycle(self):
        """Test forging a plugin end-to-end, checking policy/registry, and undoing."""
        test_plugin_name = "forge_unit_test_tool"
        target_file = Path("plugins") / f"{test_plugin_name}.py"
        if target_file.exists():
            target_file.unlink()
        reg = get_active_registry()
        if reg and reg.has(test_plugin_name):
            reg.unregister(test_plugin_name)
        policy.unregister_policy(test_plugin_name)

        code = f'''"""
Unit test forged plugin.
"""
PLUGIN = {{
    "name": "{test_plugin_name}",
    "description": "A unit test forged plugin.",
    "parameters": {{"type": "OBJECT", "properties": {{}}}},
}}

def run(parameters: dict, player=None, session_memory=None) -> str:
    return "forge unit test executed"
'''
        try:
            player_mock = MagicMock()
            player_mock.show_content = MagicMock()
            player_mock.write_log = MagicMock()

            result = forge_plugin(
                {
                    "name": test_plugin_name,
                    "description": "A unit test forged plugin.",
                    "code": code,
                    "tier": "routine",
                },
                player=player_mock,
            )
            self.assertIn("forged and hot-loaded", result)
            player_mock.show_content.assert_called_once()
            player_mock.write_log.assert_called_once()

            # Check plugin file exists on disk
            self.assertTrue(target_file.exists())

            # Check plugin is in running registry
            reg = get_active_registry()
            self.assertIsNotNone(reg)
            self.assertTrue(reg.has(test_plugin_name))
            self.assertEqual(reg.run(test_plugin_name, {}), "forge unit test executed")

            # Check policy registration
            decision = policy.decide(test_plugin_name, {})
            self.assertTrue(decision.allow)
            self.assertIs(decision.tier, policy.Tier.ROUTINE)

            # Test UNDO
            self.assertTrue(undo.can_undo())
            undo_result = undo.undo_last()
            self.assertIn("Undone: forge plugin", undo_result)

            # Verify file is deleted
            self.assertFalse(target_file.exists())

            # Verify unhooked from registry
            self.assertFalse(reg.has(test_plugin_name))

            # Verify policy tier is reverted
            reverted_decision = policy.decide(test_plugin_name, {})
            self.assertFalse(reverted_decision.allow)
            self.assertIn("unclassified", reverted_decision.reason)
        finally:
            if target_file.exists():
                target_file.unlink()
            if reg and reg.has(test_plugin_name):
                reg.unregister(test_plugin_name)
            policy.unregister_policy(test_plugin_name)


if __name__ == "__main__":
    unittest.main()
