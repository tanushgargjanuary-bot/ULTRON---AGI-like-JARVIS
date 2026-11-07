"""tests/test_native_plugin_bridges.py — Unit test suite for new native plugin bridges.

Tests crawler_bridge, minicpm_ocr_bridge, and agent_monitor_bridge against:
- Ultron plugin contract invariants (PLUGIN dict, run signature, no exceptions)
- Schema validity and required properties
- Core operations (status, help, mock runs, edge-case parameters)
- Safety and graceful degradation when external services are absent
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.plugin_loader import discover_plugins

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"


class NativePluginBridgesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = discover_plugins(PLUGINS_DIR, core_tool_names=set(), logger=lambda _m: None)

    def _call(self, name: str, **kwargs) -> str:
        res = self.registry.run(name, kwargs)
        self.assertIsInstance(res, str, f"{name} must return str, got {type(res)}")
        self.assertTrue(len(res) > 0, f"{name} returned empty string")
        return res

    # ── crawler_bridge tests ─────────────────────────────────────────────────

    def test_crawler_bridge_discovered(self):
        self.assertIn("crawler_bridge", self.registry._plugins)
        rec = self.registry._plugins["crawler_bridge"]
        self.assertEqual(rec.name, "crawler_bridge")
        self.assertTrue(rec.valid)
        self.assertIn("action", rec.parameters["properties"])
        self.assertIn("action", rec.parameters["required"])

    def test_crawler_bridge_status(self):
        text = self._call("crawler_bridge", action="status")
        self.assertIn("Crawler engine status", text)
        self.assertIn("Native parser ready", text)

    def test_crawler_bridge_markdown_conversion(self):
        raw_html = (
            "<html><head><script>alert('bad');</script><style>body{color:red;}</style></head>"
            "<body><h1>Test Heading</h1><p>Welcome to <b>Ultron</b> with a "
            "<a href='https://example.com'>link</a>.</p>"
            "<ul><li>Item 1</li><li>Item 2</li></ul>"
            "<pre><code>print('hello')</code></pre></body></html>"
        )
        text = self._call("crawler_bridge", action="markdown", raw_html=raw_html)
        self.assertIn("# Test Heading", text)
        self.assertIn("[link](https://example.com)", text)
        self.assertIn("* Item 1", text)
        self.assertIn("print('hello')", text)
        self.assertNotIn("alert('bad')", text)
        self.assertNotIn("body{color:red;}", text)

    def test_crawler_bridge_crawl_missing_url(self):
        text = self._call("crawler_bridge", action="crawl")
        self.assertIn("valid URL", text)

    def test_crawler_bridge_crawl_invalid_url(self):
        text = self._call("crawler_bridge", action="crawl", url="not_a_real_domain_12345.xyz/test")
        self.assertTrue("failed" in text.lower() or "unable" in text.lower() or "error" in text.lower())

    def test_crawler_bridge_unknown_action(self):
        text = self._call("crawler_bridge", action="unknown_op")
        self.assertIn("unknown action", text.lower())

    # ── minicpm_ocr_bridge tests ─────────────────────────────────────────────

    def test_minicpm_ocr_bridge_discovered(self):
        self.assertIn("minicpm_ocr_bridge", self.registry._plugins)
        rec = self.registry._plugins["minicpm_ocr_bridge"]
        self.assertEqual(rec.name, "minicpm_ocr_bridge")
        self.assertTrue(rec.valid)
        self.assertIn("action", rec.parameters["properties"])
        self.assertIn("action", rec.parameters["required"])

    def test_minicpm_ocr_status(self):
        text = self._call("minicpm_ocr_bridge", action="status")
        self.assertIn("MiniCPM-OCR status", text)

    def test_minicpm_ocr_help(self):
        text = self._call("minicpm_ocr_bridge", action="help")
        self.assertIn("MiniCPM-OCR Bridge", text)
        self.assertIn(".png", text)

    def test_minicpm_ocr_missing_file(self):
        text = self._call("minicpm_ocr_bridge", action="ocr", image_path="non_existent_file_98765.png")
        self.assertIn("does not exist", text)

    def test_minicpm_ocr_unsupported_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not an image")
            temp_path = f.name
        try:
            text = self._call("minicpm_ocr_bridge", action="ocr", image_path=temp_path)
            self.assertIn("Unsupported file type", text)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_minicpm_ocr_png_inspection(self):
        # 1x1 valid transparent PNG
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
            b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_bytes)
            temp_path = f.name
        try:
            text = self._call("minicpm_ocr_bridge", action="ocr", image_path=temp_path)
            self.assertIn("Document inspected", text)
            self.assertIn("1x1px", text)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_minicpm_ocr_unknown_action(self):
        text = self._call("minicpm_ocr_bridge", action="invalid_op")
        self.assertIn("unknown action", text.lower())

    # ── agent_monitor_bridge tests ───────────────────────────────────────────

    def test_agent_monitor_bridge_discovered(self):
        self.assertIn("agent_monitor_bridge", self.registry._plugins)
        rec = self.registry._plugins["agent_monitor_bridge"]
        self.assertEqual(rec.name, "agent_monitor_bridge")
        self.assertTrue(rec.valid)
        self.assertIn("action", rec.parameters["properties"])
        self.assertIn("action", rec.parameters["required"])

    def test_agent_monitor_status(self):
        text = self._call("agent_monitor_bridge", action="status")
        self.assertIn("Agent Execution Monitor", text)
        self.assertIn("Living Threads", text)

    def test_agent_monitor_threads_listing(self):
        text = self._call("agent_monitor_bridge", action="threads", verbose=True)
        self.assertIn("Active Threads", text)
        self.assertIn("MainThread", text)

    def test_agent_monitor_threads_filter(self):
        text = self._call("agent_monitor_bridge", action="threads", filter="main")
        self.assertIn("MainThread", text)

    def test_agent_monitor_tasks(self):
        text = self._call("agent_monitor_bridge", action="tasks")
        self.assertIsInstance(text, str)

    def test_agent_monitor_dashboard_probe(self):
        text = self._call("agent_monitor_bridge", action="dashboard")
        self.assertIn("whatsmyagentdoing", text)
        self.assertIn("8765", text)

    def test_agent_monitor_unknown_action(self):
        text = self._call("agent_monitor_bridge", action="random_action")
        self.assertIn("unknown action", text.lower())


if __name__ == "__main__":
    unittest.main()
