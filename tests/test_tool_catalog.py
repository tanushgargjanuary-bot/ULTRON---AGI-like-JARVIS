"""Tests for core.tool_catalog — Ultron's knowledge of its own tools."""

import unittest
from pathlib import Path

from core import tool_catalog


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = tool_catalog.build()
        cls.by_name = {entry.name: entry for entry in cls.entries}

    def test_builds_entries(self):
        self.assertGreater(len(self.entries), 20)

    def test_names_are_unique(self):
        names = [entry.name for entry in self.entries]
        self.assertEqual(len(names), len(set(names)))

    def test_inline_tools_come_from_main(self):
        self.assertIn("system_status", self.by_name)

    def test_actions_are_listed(self):
        self.assertIn("open_app", self.by_name)
        self.assertEqual(self.by_name["open_app"].kind, "action")

    def test_plugins_are_listed(self):
        self.assertIn("dev_json", self.by_name)
        self.assertEqual(self.by_name["dev_json"].kind, "plugin")
        self.assertIn("rea_bridge", self.by_name)

    def test_bridges_are_listed(self):
        for key in ("rea", "hyperframes", "hindsight", "voicestudio", "hypit"):
            entry = self.by_name[f"bridge:{key}"]
            self.assertEqual(entry.kind, "bridge")
            self.assertEqual(entry.label, key)

    def test_unavailable_tool_keeps_its_reason(self):
        # A tool that does not load must stay visible with its reason, not vanish.
        for entry in self.entries:
            if not entry.available:
                self.assertTrue(entry.reason, f"{entry.name} is silent about why")


class Render(unittest.TestCase):
    def test_render_text_names_the_counts(self):
        text = tool_catalog.render_text()
        self.assertRegex(text, r"I have \d+ tools")

    def test_grouped_puts_unavailable_last(self):
        groups = tool_catalog.grouped()
        self.assertTrue(groups)
        for items in groups.values():
            ready = [entry.available for entry in items]
            self.assertEqual(ready, sorted(ready, reverse=True))

    def test_describe_known_tool(self):
        text = tool_catalog.describe("dev_json")
        self.assertIn("dev_json", text)
        self.assertIn("plugin", text.lower())

    def test_describe_unknown_tool_says_so(self):
        text = tool_catalog.describe("no_such_tool_xyz")
        self.assertIn("no_such_tool_xyz", text)

    def test_describe_absent_bridge_states_the_blocker(self):
        entry = {e.name: e for e in tool_catalog.build()}["bridge:rea"]
        if entry.available:
            self.skipTest("REA is installed here")
        self.assertIn("not installed", tool_catalog.describe("rea").lower())


class Robust(unittest.TestCase):
    def test_missing_directories_do_not_raise(self):
        entries = toy = tool_catalog.build(include_bridges=False)
        self.assertTrue(toy)
        self.assertTrue(isinstance(entries, list))

    def test_bad_paths_give_empty_lists(self):
        self.assertEqual(tool_catalog._action_entries(Path("/nonexistent")), [])
        self.assertEqual(tool_catalog._plugin_entries(Path("/nonexistent")), [])
        self.assertEqual(tool_catalog._inline_entries(Path("/nonexistent/main.py")), [])


if __name__ == "__main__":
    unittest.main()
