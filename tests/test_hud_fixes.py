"""tests/test_hud_fixes.py — the three things the owner could see were wrong.

Reported from a screenshot of the running app: "GUI is still small and I can't
edit it", and "when Ultron started up it didn't have the multiple API thing we
decided". Rendering the interface off-screen against this tree found a third one
nobody had reported: the first-run panel was placed at (-10, -90), so its top and
left edges sat outside the window.

What is asserted here is what a person would notice:
    * identical lines in the activity log are counted, not repeated;
    * a burst of lines is not typed out over the next ten seconds;
    * the first-run screen offers more than one provider and writes nothing by
      itself;
    * the interface scale can be changed from the UI and is persisted;
    * no panel is ever placed outside the window.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QWidget

    import ui
    from memory import config_manager as cm
except ImportError as exc:      # pragma: no cover - environment without Qt
    raise unittest.SkipTest(str(exc)) from exc

APP = QApplication.instance() or QApplication([])


def type_all(widget, limit: int = 20000) -> str:
    """Run the typewriter to completion without waiting on the event loop.

    The widget schedules its next line with QTimer.singleShot, so a test either
    waits on real timers (slow and flaky) or advances it by hand. This does the
    latter: type the current line, close it, ask for the next.
    """
    for _ in range(limit):
        if not widget._queue and not widget._typing:
            break
        if widget._pos < len(widget._text):
            widget._step()
        else:
            widget._tmr.stop()
            widget._step()          # closes the line with a newline
            widget._typing = False
            widget._text = ""
            widget._next()
    return widget.toPlainText()


def finish_current_line(widget) -> None:
    while widget._pos < len(widget._text):
        widget._step()



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

class ActivityLogTests(unittest.TestCase):
    def setUp(self):
        self.log = ui.LogWidget()

    def test_a_repeated_line_is_shown_once_and_counted(self):
        # Driven through _enqueue directly: append_log goes through a queued
        # signal, and this test is about the dedupe, not about signal timing.
        for _ in range(3):
            self.log._enqueue("SYS: Ultron online.")
        text = type_all(self.log)
        self.assertEqual(text.count("SYS: Ultron online."), 1)
        self.assertIn("previous line x2", text)

    def test_different_lines_all_appear(self):
        for line in ("SYS: one", "SYS: two", "SYS: one"):
            self.log._enqueue(line)
        text = type_all(self.log)
        self.assertEqual(text.count("SYS: one"), 2)   # not consecutive: both shown
        self.assertEqual(text.count("SYS: two"), 1)

    def test_a_burst_is_not_typed_out_in_realtime(self):
        widget = ui.LogWidget()
        for i in range(6):
            widget._enqueue(f"SYS: line {i}")
        # First line types at reading speed; by the time it closes, the five
        # behind it must be handed over instantly instead of at 6 ms a character.
        finish_current_line(widget)
        widget._tmr.stop()
        widget._step()
        widget._typing = False
        widget._text = ""
        widget._next()
        self.assertEqual(widget._tmr.interval(), 0,
                         "a burst of lines must not queue behind the typewriter")


class AutoScaleTests(unittest.TestCase):
    def test_the_scale_is_never_below_one(self):
        self.assertGreaterEqual(ui._auto_ui_scale(), 1.0)

    def test_the_scale_is_capped(self):
        self.assertLessEqual(ui._auto_ui_scale(), 2.2)


class CustomizeScaleTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.dir = Path(self._temp.name)
        self._saved = (cm.CONFIG_DIR, cm.CONFIG_FILE)
        cm.CONFIG_DIR = self.dir
        cm.CONFIG_FILE = self.dir / "api_keys.json"
        self.overlay = ui.CustomizeOverlay("Ultron", "Ada", ui.DEFAULT_UI_COLOR, "Aoede")

    def tearDown(self):
        cm.CONFIG_DIR, cm.CONFIG_FILE = self._saved
        self._temp.cleanup()

    def test_the_panel_offers_a_choice_of_scales(self):
        self.assertGreaterEqual(len(self.overlay._scale_btns), 4)
        self.assertIn(1.45, self.overlay._scale_btns)

    def test_picking_a_scale_persists_it(self):
        self.overlay._on_scale_pick(1.45)
        self.assertEqual(cm.get_ui_scale(), 1.45)

    def test_picking_a_scale_offers_the_restart(self):
        self.assertTrue(self.overlay._restart_btn.isHidden())
        self.overlay._on_scale_pick(1.3)
        self.assertFalse(self.overlay._restart_btn.isHidden())
        self.assertIn("restart", self.overlay._scale_hint.text())

    def test_the_current_scale_is_highlighted(self):
        self.overlay._on_scale_pick(1.3)
        checked = [v for v, b in self.overlay._scale_btns.items() if b.isChecked()]
        self.assertEqual(checked, [1.3])


class SetupScreenTests(unittest.TestCase):
    def setUp(self):
        # Sandboxed: "writes nothing" is only a meaningful claim about a known
        # location. Without this the test passes or fails depending on whether
        # some earlier test (or a stray render) left a real config behind — which
        # is exactly what happened the first time it ran in the full suite.
        self._temp = tempfile.TemporaryDirectory()
        self.dir = Path(self._temp.name)
        self._saved = (cm.CONFIG_DIR, cm.CONFIG_FILE)
        cm.CONFIG_DIR = self.dir
        cm.CONFIG_FILE = self.dir / "api_keys.json"
        self.overlay = ui.SetupOverlay()
        self.emitted: list[dict] = []
        self.overlay.done.connect(self.emitted.append)

    def tearDown(self):
        cm.CONFIG_DIR, cm.CONFIG_FILE = self._saved
        self._temp.cleanup()

    def test_it_offers_the_providers_the_app_knows(self):
        self.assertGreaterEqual(len(self.overlay._catalog), 5)
        labels = [entry["label"] for entry in self.overlay._catalog]
        self.assertIn("Ollama", labels)
        self.assertIn("Groq", labels)

    def test_a_local_service_is_prefilled_and_asks_for_no_key(self):
        index = next(i for i, e in enumerate(self.overlay._catalog) if e["id"] == "ollama")
        self.overlay._svc_combo.setCurrentIndex(index)
        self.assertTrue(self.overlay._base_input.text().startswith("http"))
        self.assertFalse(self.overlay._prov_key_input.isEnabled())

    def test_a_cloud_service_asks_for_a_key(self):
        index = next(i for i, e in enumerate(self.overlay._catalog) if e["id"] == "groq")
        self.overlay._svc_combo.setCurrentIndex(index)
        self.assertTrue(self.overlay._prov_key_input.isEnabled())

    def test_nothing_is_submitted_with_neither_a_key_nor_a_provider(self):
        self.overlay._submit()
        self.assertEqual(self.emitted, [])
        self.assertIn("at least one provider", self.overlay._error.text())

    def test_a_gemini_key_alone_is_a_complete_answer(self):
        self.overlay._key_input.setText("AIza-test-key")
        self.overlay._submit()
        self.assertEqual(len(self.emitted), 1)
        self.assertEqual(self.emitted[0]["gemini_api_key"], "AIza-test-key")
        self.assertEqual(self.emitted[0]["providers"], [])

    def test_several_providers_can_be_added_and_removed(self):
        for service, key in (("groq", "gsk-1"), ("openai", "sk-2")):
            index = next(i for i, e in enumerate(self.overlay._catalog) if e["id"] == service)
            self.overlay._svc_combo.setCurrentIndex(index)
            self.overlay._model_input.setText("a-model")
            self.overlay._prov_key_input.setText(key)
            self.overlay._add_provider()
        self.assertEqual(len(self.overlay._added), 2)
        self.overlay._submit()
        ids = [row["id"] for row in self.emitted[0]["providers"]]
        self.assertEqual(ids, ["openai_compat@groq", "openai_compat@openai"])

        self.overlay._remove_provider("openai_compat@groq")
        self.assertEqual([row["id"] for row in self.overlay._added],
                         ["openai_compat@openai"])

    def test_an_incomplete_provider_is_refused_with_a_reason(self):
        self.overlay._base_input.setText("")
        self.overlay._add_provider()
        self.assertEqual(self.overlay._added, [])
        self.assertIn("address", self.overlay._error.text())

    def test_the_screen_writes_nothing_itself(self):
        # It emits; MainWindow writes. A setup screen that writes on open is how
        # a half-filled dialog ends up as a broken config.
        cm.CONFIG_FILE.write_text('{"ui_scale": 1.3}', encoding="utf-8")
        before = cm.CONFIG_FILE.read_bytes()
        self.overlay._key_input.setText("AIza-test-key")
        self.overlay._submit()
        self.assertEqual(cm.CONFIG_FILE.read_bytes(), before,
                         "the first-run screen must not touch the config file")


class OverlayPlacementTests(unittest.TestCase):
    def test_the_first_run_panel_is_inside_the_window(self):
        window = ui.MainWindow(str(ROOT / "core" / "face_model.obj"))
        try:
            window.resize(1600, 900)
            APP.processEvents()
            panel = getattr(window, "_overlay", None)
            if panel is None:
                self.skipTest("no setup panel: this environment is configured")
            window._place_overlay(panel, ui.SetupOverlay._OW, ui.SetupOverlay._OH)
            geo = panel.geometry()
            central = window.centralWidget().size()
            self.assertGreaterEqual(geo.x(), 0)
            self.assertGreaterEqual(geo.y(), 0)
            self.assertLessEqual(geo.x() + geo.width(), central.width())
            self.assertLessEqual(geo.y() + geo.height(), central.height())
        finally:
            window.close()

    def test_a_panel_larger_than_the_window_is_shrunk_to_fit(self):
        window = ui.MainWindow(str(ROOT / "core" / "face_model.obj"))
        try:
            window.resize(900, 700)
            panel = QWidget(window.centralWidget())
            window._place_overlay(panel, 4000, 4000)
            central = window.centralWidget().size()
            self.assertLessEqual(panel.width(), central.width())
            self.assertLessEqual(panel.height(), central.height())
        finally:
            window.close()


class CoreColourFade(unittest.TestCase):
    """A change of state is a movement, not a cut.

    The old code picked two colours straight from the state and drew them, so a
    switch from listening to thinking changed the accent from green to violet in
    one frame. That reads as a glitch. The colours are eased now, and these tests
    pin the two things a person would notice: the change is gradual, and it does
    arrive.
    """

    def setUp(self):
        from PyQt6.QtWidgets import QApplication
        import ui

        self.app = QApplication.instance() or QApplication([])
        self.canvas = ui.HudCanvas(None)      # no face image: the avatar path
        self.canvas.state = "IDLE"
        self.canvas.speaking = False
        self.canvas.muted = False

    def tearDown(self):
        self.canvas.deleteLater()

    def test_the_first_colour_is_the_state_colour_with_no_fade_in(self):
        self.canvas.state = "LISTENING"
        self.canvas._ease_core_colours(1 / 60)
        drawn = self.canvas._core_colours()[1]
        target = self.canvas._core_colours_for_state()[1]
        self.assertEqual(drawn.name(), target.name())

    def test_a_state_change_moves_the_colour_and_does_not_jump(self):
        self.canvas._ease_core_colours(1 / 60)                 # settle on IDLE
        start = self.canvas._core_colours()[1].name()
        self.canvas.state = "THINKING"
        self.canvas._ease_core_colours(1 / 60)
        after_one_frame = self.canvas._core_colours()[1].name()
        target = self.canvas._core_colours_for_state()[1].name()
        self.assertNotEqual(after_one_frame, target, "one frame must not complete the fade")
        self.assertNotEqual(after_one_frame, start, "one frame must still move")
        for _ in range(120):
            self.canvas._ease_core_colours(1 / 60)
        self.assertEqual(self.canvas._core_colours()[1].name(), target,
                         "two seconds must be enough to arrive")

    def test_a_broken_colour_source_falls_back_instead_of_raising(self):
        def explode():
            raise RuntimeError("no palette")

        self.canvas._core_colours_for_state = explode
        self.canvas._ease_core_colours(1 / 60)                 # must not raise
        self.assertIsNone(self.canvas._core_a)


if __name__ == "__main__":
    unittest.main()
