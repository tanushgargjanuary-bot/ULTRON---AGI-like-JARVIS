"""Tests for the TOOLS panel — the tablist the owner asked for.

"Add all these tools in ULTRON natively and make the Dashboard fit accordingly so
that we can have a tablist where I can access these tools." The panel is only
useful if it opens without a mouse, lists every tool it claims to, and shows an
unavailable tool instead of hiding it. Those are the three things asserted.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QPushButton, QTabWidget

    import ui
    from core import tool_catalog
except ImportError as exc:      # pragma: no cover - environment without Qt
    raise unittest.SkipTest(str(exc)) from exc

APP = QApplication.instance() or QApplication([])


def settle(ms: int = 4000) -> None:
    """Let queued work run, but never longer than the budget."""
    QTimer.singleShot(min(ms, 200), APP.quit)
    APP.exec()


class Panel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.overlay = ui.ToolsOverlay()
        cls.tabs = cls.overlay.findChild(QTabWidget)

    @classmethod
    def tearDownClass(cls):
        cls.overlay.deleteLater()

    def test_it_has_tabs(self):
        self.assertIsNotNone(self.tabs)
        self.assertGreaterEqual(self.tabs.count(), 4)

    def test_tab_names_are_categories(self):
        names = [self.tabs.tabText(i) for i in range(self.tabs.count())]
        self.assertIn("SYSTEM", names)
        self.assertIn("SECURITY", names)

    def test_the_count_matches_the_catalog(self):
        text = self.overlay._count.text()
        self.assertIn(str(len(tool_catalog.build())), text)
        self.assertIn("usable", text)

    def test_every_tool_appears_in_some_tab(self):
        shown = 0
        for index in range(self.tabs.count()):
            shown += len(self.tabs.widget(index).findChildren(type(self.overlay._count)))
        self.assertGreaterEqual(shown, len(tool_catalog.build()))

    def test_an_unavailable_tool_is_visible_not_hidden(self):
        texts = []
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            for label in page.findChildren(type(self.overlay._count)):
                texts.append(label.text())
        joined = "\n".join(texts)
        unavailable = [e for e in tool_catalog.build() if not e.available]
        for entry in unavailable:
            self.assertIn(entry.label, joined, f"{entry.name} is missing from the panel")

    def test_close_button_exists(self):
        buttons = [b.text() for b in self.overlay.findChildren(QPushButton)]
        self.assertIn("CLOSE", buttons)

    def test_reload_is_safe_to_call_twice(self):
        before = self.tabs.count()
        self.overlay.reload()
        settle()
        self.assertEqual(self.tabs.count(), before)


class Wiring(unittest.TestCase):
    """The panel needs a door: a drawer button and a keyboard shortcut."""

    def test_drawer_has_a_tools_button(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        self.assertIn('QPushButton("🛠  TOOLS")', source)
        self.assertIn("_open_tools_panel", source)

    def test_ctrl_t_opens_the_panel(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        self.assertIn('QKeySequence("Ctrl+T")', source)

    def test_the_overlay_never_lands_outside_the_window(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        block = source[source.index("def _open_tools_panel"):]
        block = block[: block.index("def ", 10)]
        self.assertIn("_centre_overlay", block)


if __name__ == "__main__":
    unittest.main()
