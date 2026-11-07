"""tests/test_context_detector.py — Tests for active window & clipboard context detection."""

import unittest
from unittest.mock import MagicMock, patch

from core import context_detector, tool_prompt


class TestContextDetector(unittest.TestCase):
    def test_detect_active_categories_empty_when_unknown(self):
        with patch("custom_jarvis.tools.get_active_window") as mock_gw:
            mock_res = MagicMock()
            mock_res.data = {"process_name": "calc.exe", "title": "Calculator"}
            mock_gw.return_value = mock_res
            cats = context_detector.detect_active_categories()
            self.assertEqual(cats, [])

    def test_detect_active_categories_developer_for_ide(self):
        with patch("custom_jarvis.tools.get_active_window") as mock_gw:
            mock_res = MagicMock()
            mock_res.data = {"process_name": "code.exe", "title": "main.py - project - Visual Studio Code"}
            mock_gw.return_value = mock_res
            cats = context_detector.detect_active_categories()
            self.assertIn("developer", cats)
            self.assertIn("files", cats)

    def test_detect_active_categories_knowledge_for_browser(self):
        with patch("custom_jarvis.tools.get_active_window") as mock_gw:
            mock_res = MagicMock()
            mock_res.data = {"process_name": "chrome.exe", "title": "GitHub Awesome - Google Chrome"}
            mock_gw.return_value = mock_res
            cats = context_detector.detect_active_categories()
            self.assertEqual(cats, ["knowledge"])

    def test_detect_active_categories_handles_exceptions_gracefully(self):
        with patch("custom_jarvis.tools.get_active_window", side_effect=RuntimeError("COM error")):
            cats = context_detector.detect_active_categories()
            self.assertEqual(cats, [])

    def test_get_clipboard_target_valid_url(self):
        with patch("pyperclip.paste", return_value="https://github.com/trending"):
            target = context_detector.get_clipboard_target()
            self.assertEqual(target, "https://github.com/trending")

    def test_get_clipboard_target_ignores_non_target(self):
        with patch("pyperclip.paste", return_value="just some random text"):
            target = context_detector.get_clipboard_target()
            self.assertEqual(target, "")

    def test_tool_prompt_describe_reorders_priority_categories(self):
        decls = [
            {"name": "web_search", "description": "WHEN you need to search online — searches Google."},
            {"name": "code_helper", "description": "WHEN the user needs code — writes and reviews code."},
        ]
        # Without priority: original order
        normal = tool_prompt.describe(decls)
        self.assertTrue(normal.startswith("- web_search"))

        # With developer priority: code_helper floats to top
        reordered = tool_prompt.describe(decls, priority_categories=["developer", "files"])
        self.assertTrue(reordered.startswith("- code_helper"))


if __name__ == "__main__":
    unittest.main()
