"""tests/test_bugfix_pass.py — defects found by reading the code, not by looking.

The screenshot the owner sent found five; reading the paths it came through found
nine more, and two of those were in the fixes for the first five. Each class here
is one of them, and each test fails without its fix. The order is the order they
were found.

    ConfigFileTests             a corrupt api_keys.json used to be overwritten
    AtomicWriteTests            a crash mid-write used to leave a truncated file
    UiScaleRangeTests           a stored 4.0 made the panel that fixes it unusable
    WindowSizeTests             a remembered size has to be sane or ignored
    FirstRunEdgeTests           providers[0] was indexed even when skipped
    CustomizeScaleControlTests  ±/AUTO, clamping, and the restart offer
    OverlayGeometryTests        resizeEvent squashed the setup panel to 460x390
    RestartTests                the relaunch inherited the old scale factor
    SetupScreenTests            stylesheet growth, address validation, empty catalog
    SetupFailureTests           a save failure was printed to a console nobody has
    ReconnectWiringTests        main.py's numbers agree with the policy's

Two of these can only be checked at the source level — main.py imports
sounddevice, and the reconnect loop needs a live session — and they say so.
"""

from __future__ import annotations

import ast
import json
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


class Sandboxed(unittest.TestCase):
    """Point config_manager at a temporary directory for one test."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.dir = Path(self._temp.name)
        self._saved = (cm.CONFIG_DIR, cm.CONFIG_FILE)
        cm.CONFIG_DIR = self.dir
        cm.CONFIG_FILE = self.dir / "api_keys.json"

    def tearDown(self):
        cm.CONFIG_DIR, cm.CONFIG_FILE = self._saved
        self._temp.cleanup()

    def write(self, text: str):
        cm.CONFIG_FILE.write_text(text, encoding="utf-8")


# ── the config file ─────────────────────────────────────────────────────────

class ConfigFileTests(Sandboxed):
    def test_a_corrupt_file_is_kept_not_quietly_replaced(self):
        # Half a file, as a power cut leaves it. Saving an unrelated setting used
        # to read this as {}, then write one key over it: every provider key the
        # user had typed was gone, because they changed a colour.
        self.write('{"gemini_api_key": "AIzaSyBREAK')
        cm.save_ui_scale(1.3)
        kept = list(self.dir.glob("api_keys.json.broken-*"))
        self.assertEqual(len(kept), 1, "the damaged file must be preserved")
        self.assertIn("AIzaSyBREAK", kept[0].read_text(encoding="utf-8"))
        self.assertEqual(cm.get_ui_scale(), 1.3, "the new setting still saves")

    def test_a_valid_file_is_not_copied_anywhere(self):
        self.write(json.dumps({"os_system": "windows"}))
        cm.save_ui_scale(1.3)
        self.assertEqual(list(self.dir.glob("*.broken-*")), [])

    def test_a_json_list_is_treated_as_damage_not_as_a_config(self):
        self.write("[1, 2, 3]")
        cm.save_ui_scale(1.3)
        self.assertEqual(cm.get_ui_scale(), 1.3)
        self.assertEqual(len(list(self.dir.glob("api_keys.json.broken-*"))), 1)

    def test_saving_one_setting_keeps_every_other_one(self):
        self.write(json.dumps({"os_system": "windows", "assistant_name": "Ultron",
                               "providers": {"mode": "pipeline",
                                             "creds": {"openai_compat@groq": {"api_key": "k"}}}}))
        cm.save_ui_scale(1.3)
        cfg = json.loads(cm.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertEqual(cfg["assistant_name"], "Ultron")
        self.assertIn("openai_compat@groq", cfg["providers"]["creds"])


class LoadApiKeysTests(Sandboxed):
    def test_a_json_list_does_not_reach_a_caller_that_wants_a_dict(self):
        # It parsed, so it was returned, and the next .get() raised AttributeError
        # at start-up in whichever setting was read first.
        for text in ("[1, 2]", '"just a string"', "42", "null"):
            self.write(text)
            self.assertEqual(cm.load_api_keys(), {}, text)
            self.assertEqual(cm.get_ui_scale(), 0.0, text)
            self.assertFalse(cm.has_a_brain(), text)

    def test_the_old_setter_uses_the_safe_write_too(self):
        # It was the last open-coded read-modify-write in the file.
        self.write('{"assistant_name": "Ultron"')
        cm.save_api_keys("AIza-a-key")
        self.assertEqual(len(list(self.dir.glob("api_keys.json.broken-*"))), 1)
        self.assertEqual(cm.load_api_keys().get("gemini_api_key"), "AIza-a-key")

    def test_the_old_setter_keeps_the_other_settings(self):
        self.write(json.dumps({"os_system": "windows", "assistant_name": "Ultron"}))
        cm.save_api_keys("  AIza-a-key  ")
        cfg = cm.load_api_keys()
        self.assertEqual(cfg["assistant_name"], "Ultron")
        self.assertEqual(cfg["gemini_api_key"], "AIza-a-key")


class AtomicWriteTests(Sandboxed):
    def test_no_temporary_file_is_left_behind(self):
        cm.save_ui_scale(1.3)
        self.assertEqual(list(self.dir.glob("*.tmp")), [])

    def test_the_write_replaces_rather_than_truncates(self):
        # A replace can only ever show the old file or the new one; a truncated
        # destination is exactly the damage ConfigFileTests is about.
        self.write(json.dumps({"os_system": "windows"}))
        cm.save_ui_scale(1.4)
        parsed = json.loads(cm.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertEqual(parsed, {"os_system": "windows", "ui_scale": 1.4})


# ── the interface scale, as a stored number ─────────────────────────────────

class UiScaleRangeTests(Sandboxed):
    def test_a_scale_beyond_the_ceiling_is_clamped_on_the_way_in(self):
        # 4.0 draws the Customise panel — the only way to undo it — off the
        # bottom of the screen, and the user is editing JSON again.
        cm.save_ui_scale(4.0)
        self.assertEqual(cm.get_ui_scale(), cm.UI_SCALE_MAX)

    def test_a_scale_below_the_floor_is_clamped_on_the_way_in(self):
        cm.save_ui_scale(0.10)
        self.assertEqual(cm.get_ui_scale(), cm.UI_SCALE_MIN)

    def test_a_hand_edited_number_outside_the_range_means_automatic(self):
        # get_ui_scale is the last line of defence: nothing else reads the file.
        for value in (0.05, 9, -3):
            self.write(json.dumps({"ui_scale": value}))
            self.assertEqual(cm.get_ui_scale(), 0.0, value)

    def test_nonsense_in_the_file_means_automatic_rather_than_a_crash(self):
        for value in ("big", None, [], {}, True):
            self.write(json.dumps({"ui_scale": value}))
            self.assertIsInstance(cm.get_ui_scale(), float, value)

    def test_zero_means_work_it_out_and_is_always_accepted(self):
        self.write(json.dumps({"ui_scale": 0}))
        self.assertEqual(cm.get_ui_scale(), 0.0)
        cm.reset_ui_scale()
        self.assertEqual(cm.get_ui_scale(), 0.0)

    def test_a_normal_value_round_trips(self):
        for value in (0.9, 1.0, 1.4, 1.45, 2.0, 2.5):
            cm.save_ui_scale(value)
            self.assertEqual(cm.get_ui_scale(), value)


class WindowSizeTests(Sandboxed):
    def test_a_size_round_trips(self):
        cm.save_window_size(1280, 800)
        self.assertEqual(cm.get_window_size(), (1280, 800))

    def test_nothing_saved_means_the_designed_default(self):
        self.assertEqual(cm.get_window_size(), (0, 0))

    def test_an_impossible_size_is_ignored_rather_than_restored(self):
        # A monitor that is no longer attached must not open the window off-screen.
        cm.save_window_size(99999, 99999)
        self.assertEqual(cm.get_window_size(), (0, 0))
        cm.save_window_size(10, 10)
        self.assertEqual(cm.get_window_size(), (0, 0))

    def test_junk_in_the_file_does_not_raise(self):
        for value in ("big", None, [1], {"w": 2}, [1, "x"]):
            self.write(json.dumps({"window_size": value}))
            self.assertEqual(cm.get_window_size(), (0, 0), value)


# ── first run ───────────────────────────────────────────────────────────────

class FirstRunEdgeTests(Sandboxed):
    def test_a_skipped_row_cannot_break_the_save(self):
        # `providers[0]` was indexed after the loop that skips non-dict rows, so
        # this combination raised AttributeError *inside the save path* — after
        # the first-run screen had already been dismissed.
        cfg = cm.apply_first_run(
            os_name="windows",
            providers=[None, {"id": "", "values": {}},
                       {"id": "openai_compat@ollama",
                        "values": {"base_url": "http://127.0.0.1:11434/v1",
                                   "model": "qwen3:8b"}}])
        self.assertEqual(cfg["providers"]["pipeline"]["llm"], "openai_compat@ollama")
        self.assertEqual(cfg["providers"]["mode"], cm.PROVIDER_MODE_PIPELINE)

    def test_all_rows_blank_writes_no_provider_block_at_all(self):
        cfg = cm.apply_first_run(os_name="windows",
                                 providers=[{"id": "openai_compat@groq", "values": {"api_key": ""}}])
        self.assertNotIn("providers", cfg)
        self.assertFalse(cm.has_a_brain())

    def test_a_provider_and_no_gemini_key_starts_the_app(self):
        cm.apply_first_run(os_name="windows", providers=[
            {"id": "openai_compat@ollama",
             "values": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:8b"}}])
        self.assertTrue(cm.has_a_brain())
        self.assertEqual(cm.get_ui_scale(), 0.0, "setup must not invent a scale")


# ── the Customise panel's scale control ─────────────────────────────────────

class CustomizeScaleControlTests(Sandboxed):
    def setUp(self):
        super().setUp()
        self.overlay = ui.CustomizeOverlay("Ultron", "Ada", ui.DEFAULT_UI_COLOR, "Aoede")

    def test_the_stepper_moves_one_step_at_a_time(self):
        self.overlay._on_scale_pick(1.30)
        self.overlay._nudge_scale(+1)
        self.assertEqual(cm.get_ui_scale(), 1.35)
        self.overlay._nudge_scale(-1)
        self.assertEqual(cm.get_ui_scale(), 1.30)

    def test_the_stepper_stops_at_the_ceiling(self):
        self.overlay._on_scale_pick(cm.UI_SCALE_MAX)
        for _ in range(5):
            self.overlay._nudge_scale(+1)
        self.assertEqual(cm.get_ui_scale(), cm.UI_SCALE_MAX)

    def test_the_stepper_stops_at_the_floor(self):
        self.overlay._on_scale_pick(cm.UI_SCALE_MIN)
        for _ in range(5):
            self.overlay._nudge_scale(-1)
        self.assertEqual(cm.get_ui_scale(), cm.UI_SCALE_MIN)

    def test_a_wild_value_from_a_caller_is_clamped(self):
        self.overlay._on_scale_pick(99)
        self.assertEqual(cm.get_ui_scale(), cm.UI_SCALE_MAX)
        self.overlay._on_scale_pick(-2)
        self.assertEqual(cm.get_ui_scale(), cm.UI_SCALE_MIN)

    def test_automatic_writes_zero_and_says_what_it_works_out_as(self):
        self.overlay._on_scale_pick(1.85)
        self.overlay._on_auto_scale()
        self.assertEqual(cm.get_ui_scale(), 0.0)
        self.assertTrue(self.overlay._auto_btn.isChecked())
        self.assertIn("automatic", self.overlay._scale_hint.text())

    def test_the_auto_button_is_off_when_a_preset_is_chosen(self):
        self.overlay._on_scale_pick(1.45)
        self.assertFalse(self.overlay._auto_btn.isChecked())

    def test_a_change_always_offers_the_restart(self):
        self.assertTrue(self.overlay._restart_btn.isHidden())
        self.overlay._nudge_scale(+1)
        self.assertFalse(self.overlay._restart_btn.isHidden())

    def test_the_keyboard_shortcuts_are_connected(self):
        # Ctrl+= / Ctrl+- / Ctrl+0 / Ctrl+Shift+R exist as shortcuts on the window.
        w = ui.MainWindow("face.png")
        keys = {s.key().toString() for s in w.findChildren(ui.QShortcut)}
        for expected in ("Ctrl+=", "Ctrl+-", "Ctrl+0", "Ctrl+Shift+R"):
            self.assertIn(expected, keys)

    def test_the_window_saves_a_narrower_scale_from_the_keyboard(self):
        w = ui.MainWindow("face.png")
        cm.save_ui_scale(1.40)
        w._scale_step(-1)
        self.assertEqual(cm.get_ui_scale(), 1.35)
        w._scale_auto()
        self.assertEqual(cm.get_ui_scale(), 0.0)


# ── where the panels sit ────────────────────────────────────────────────────

class OverlayGeometryTests(Sandboxed):
    def setUp(self):
        super().setUp()
        self.win = ui.MainWindow("face.png")
        self.win.resize(1280, 800)

    def test_a_resize_does_not_squash_the_setup_panel(self):
        # resizeEvent hardcoded 460x390 for this panel — a size that belongs to a
        # different dialog — so any resize put the first-run screen at two-thirds
        # of its size with its contents in the wrong place.
        import PyQt6.QtGui as QtGui
        self.win._show_setup()
        panel = self.win._overlay
        self.assertIsNotNone(panel)
        cw = self.win.centralWidget()
        self.win.resizeEvent(QtGui.QResizeEvent(self.win.size(), self.win.size()))
        self.assertNotEqual((panel.width(), panel.height()), (460, 390))
        self.assertEqual(
            (panel.width(), panel.height()),
            (min(ui.SetupOverlay._OW, cw.width() - 24),
             min(ui.SetupOverlay._OH, cw.height() - 24)))

    def test_a_panel_larger_than_the_window_still_starts_inside_it(self):
        panel = QWidget(self.win.centralWidget())
        self.win.resize(400, 300)
        self.win._place_overlay(panel, 900, 900)
        geo = panel.geometry()
        self.assertGreaterEqual(geo.x(), 0)
        self.assertGreaterEqual(geo.y(), 0)
        self.assertLessEqual(geo.width(), self.win.centralWidget().width())
        self.assertLessEqual(geo.height(), self.win.centralWidget().height())

    def test_the_panel_is_centred_in_a_roomy_window(self):
        panel = QWidget(self.win.centralWidget())
        self.win.resize(1400, 900)
        cw = self.win.centralWidget()
        self.win._place_overlay(panel, 600, 600)
        self.assertAlmostEqual(panel.geometry().center().x(), cw.rect().center().x(),
                               delta=2)
        self.assertAlmostEqual(panel.geometry().center().y(), cw.rect().center().y(),
                               delta=2)

    def test_the_window_never_opens_larger_than_the_screen(self):
        from PyQt6.QtWidgets import QApplication as _App
        avail = _App.primaryScreen().availableGeometry()
        w = ui.MainWindow("face.png")
        self.assertLessEqual(w.width(), avail.width())
        self.assertLessEqual(w.height(), avail.height())
        self.assertLessEqual(w.minimumWidth(), avail.width())
        self.assertLessEqual(w.minimumHeight(), avail.height())


# ── the relaunch ────────────────────────────────────────────────────────────

class RestartTests(Sandboxed):
    def test_the_relaunch_does_not_inherit_the_old_scale_factor(self):
        # _apply_ui_scale sets QT_SCALE_FACTOR in this process. A child that
        # inherits it sees the variable already set and keeps the OLD scale, so
        # "restart to apply" restarted to no effect at all.
        import PyQt6.QtCore as QtCore

        captured = {}

        class FakeProcess:
            @staticmethod
            def startDetached(program, arguments, env, **kwargs):
                captured["program"] = program
                captured["arguments"] = list(arguments)
                captured["scale"] = env.value("QT_SCALE_FACTOR")
                captured["has_env"] = True
                return True, 1234

        os.environ["QT_SCALE_FACTOR"] = "1.40"
        real = QtCore.QProcess
        QtCore.QProcess = FakeProcess
        try:
            w = ui.MainWindow("face.png")
            w._restart_app()
        finally:
            QtCore.QProcess = real
            os.environ.pop("QT_SCALE_FACTOR", None)

        self.assertIn("has_env", captured, "the child must get an explicit environment")
        self.assertFalse(captured["scale"],
                         "QT_SCALE_FACTOR must not be inherited by the relaunch")
        self.assertEqual(captured["program"], sys.executable)
        self.assertEqual(captured["arguments"][0], sys.argv[0])

    def test_a_failed_relaunch_says_so_instead_of_closing_the_app(self):
        import PyQt6.QtCore as QtCore

        class BrokenProcess:
            @staticmethod
            def startDetached(*_a, **_k):
                return False, 0

        real = QtCore.QProcess
        QtCore.QProcess = BrokenProcess
        closed = []
        try:
            w = ui.MainWindow("face.png")
            w.close = lambda: closed.append(True)
            w._restart_app()
        finally:
            QtCore.QProcess = real
        self.assertEqual(closed, [], "a failed relaunch must not close the app")
        APP.processEvents()          # append_log crosses threads through a signal
        from tests.test_hud_fixes import type_all
        self.assertIn("Could not restart", type_all(w._log))


# ── the first-run screen ────────────────────────────────────────────────────

class SetupScreenTextTests(Sandboxed):
    def setUp(self):
        super().setUp()
        self.overlay = ui.SetupOverlay()

    def test_a_repeated_failed_click_does_not_grow_the_stylesheet(self):
        self.overlay._submit()
        first = self.overlay._key_input.styleSheet()
        for _ in range(5):
            self.overlay._submit()
        self.assertEqual(self.overlay._key_input.styleSheet(), first)

    def test_typing_a_key_clears_the_red_border(self):
        from ui import C
        self.overlay._submit()
        self.assertIn(C.RED.lower(), self.overlay._key_input.styleSheet().lower())
        self.overlay._key_input.setText("AIza-test")
        self.overlay._submit()
        self.assertNotIn(C.RED.lower(), self.overlay._key_input.styleSheet().lower())

    def test_an_address_without_a_scheme_is_refused(self):
        idx = next(i for i, e in enumerate(self.overlay._catalog)
                   if e["id"] == "ollama")
        self.overlay._svc_combo.setCurrentIndex(idx)
        self.overlay._base_input.setText("127.0.0.1:11434")
        self.overlay._model_input.setText("qwen3:8b")
        self.overlay._add_provider()
        self.assertEqual(self.overlay._added, [])
        self.assertIn("http://", self.overlay._error.text())

    def test_an_empty_provider_catalog_still_opens(self):
        # _current_entry indexes [0]: an empty CATALOG was a crash on first click.
        import providers.llm_openai as llm_openai
        real = llm_openai.CATALOG
        llm_openai.CATALOG = []
        try:
            overlay = ui.SetupOverlay()
        finally:
            llm_openai.CATALOG = real
        self.assertTrue(overlay._catalog)
        self.assertIsInstance(overlay._current_entry(), dict)

    def test_hiding_it_repaints_the_hud_underneath(self):
        # It sits in no layout, so Qt never invalidates what it covered: without
        # this the panel's last frame stays on screen as a ghost.
        self.assertIn("hideEvent", type(self.overlay).__dict__)


class OneSetupPanelAtATimeTests(Sandboxed):
    def test_asking_twice_does_not_stack_two_panels(self):
        # prompt_reconfig fires on every rejected key. Each call built another
        # overlay on top of the last, and the older panel was still connected to
        # the same handler, so answers went to a screen the user could not see.
        w = ui.MainWindow("face.png")
        w._show_setup()
        first = w._overlay
        w._show_setup()
        self.assertIs(w._overlay, first)
        # Counted as children rather than as "visible": off-screen, with the
        # window itself never shown, nothing reports itself visible.
        panels = w.centralWidget().findChildren(ui.SetupOverlay)
        self.assertEqual(len(panels), 1, "one panel, not a stack of them")

    def test_a_finished_setup_leaves_nothing_behind(self):
        w = ui.MainWindow("face.png")
        w._show_setup()
        w._on_setup_done({"os": "windows", "gemini_api_key": "AIza-test", "providers": []})
        self.assertIsNone(w._overlay)
        self.assertEqual([c for c in w.centralWidget().findChildren(ui.SetupOverlay)
                          if c.isVisible()], [])


class SetupFailureTests(Sandboxed):
    def test_a_failed_save_is_reported_on_screen(self):
        w = ui.MainWindow("face.png")

        def boom(**_kwargs):
            raise OSError("disk is full")

        real = cm.apply_first_run
        cm.apply_first_run = boom
        try:
            w._on_setup_done({"os": "windows", "gemini_api_key": "AIza-test",
                              "providers": []})
        finally:
            cm.apply_first_run = real
        from tests.test_hud_fixes import type_all
        text = type_all(w._log)
        self.assertIn("ERR:", text)
        self.assertIn("disk is full", text)

    def test_an_install_that_is_still_not_configured_is_not_called_ready(self):
        w = ui.MainWindow("face.png")
        real = cm.apply_first_run

        def boom(**_kwargs):
            raise OSError("disk is full")

        cm.apply_first_run = boom
        try:
            w._on_setup_done({"os": "windows", "gemini_api_key": "", "providers": []})
        finally:
            cm.apply_first_run = real
        self.assertFalse(w._ready)


# ── main.py's numbers, which cannot be imported here ───────────────────────

class ReconnectWiringTests(unittest.TestCase):
    """main.py imports sounddevice, and the loop needs a live session.

    So these read the source. That is a weaker kind of test and it is the honest
    one available: each assertion is a line that was wrong and is now right.
    """

    def setUp(self):
        self.src = (ROOT / "main.py").read_text(encoding="utf-8")
        self.tree = ast.parse(self.src)

    def test_one_number_for_the_starting_delay(self):
        self.assertIn("_RECONNECT_BASE = float(_reconnect.BASE_DELAY)", self.src)

    def test_no_branch_stores_a_zero_delay(self):
        # Every "= 0" here is how the hot loop came back by another road: the
        # net-error branch doubled it and retried in the same instant.
        for line in self.src.splitlines():
            stripped = line.strip()
            if stripped.startswith("self._conn_backoff = "):
                self.assertNotEqual(stripped, "self._conn_backoff = 0",
                                    "a stored delay of zero is a spin loop")

    def test_a_successful_connect_resets_the_delay_as_well_as_the_streak(self):
        start = self.src.index("self._conn_streak = 0")
        window = self.src[start:start + 900]
        self.assertIn("self._conn_backoff = _RECONNECT_BASE", window)

    def test_the_network_backoff_is_floored_and_capped_like_the_policy(self):
        self.assertIn("max(_RECONNECT_BASE, _prev * 2)", self.src)
        self.assertIn("_reconnect.MAX_DELAY", self.src)

    def test_a_successful_connect_is_still_where_the_streak_resets(self):
        self.assertGreaterEqual(self.src.count("self._conn_streak = 0"), 2)


class SecretBackupIgnoreTests(unittest.TestCase):
    """The new backup files contain the same secrets as the files they protect."""

    def patterns(self) -> list[str]:
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        return [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]

    def test_the_ones_this_build_writes_are_covered(self):
        patterns = self.patterns()
        self.assertIn("config/api_keys.json.*", patterns)
        self.assertIn("memory/long_term.json.bak-*", patterns)

    def test_no_pattern_carries_a_trailing_comment(self):
        # The lesson the existing test records: git has no trailing comments.
        self.assertEqual([ln for ln in self.patterns() if "#" in ln], [])

    def test_git_agrees_if_git_is_here(self):
        import shutil
        import subprocess
        git = shutil.which("git")
        if not git:
            raise unittest.SkipTest("git is not installed here")
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            subprocess.run([git, "init", "-q", str(repo)], check=True)
            (repo / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
            (repo / "config").mkdir()
            (repo / "memory").mkdir()
            for name in ("config/api_keys.json",
                         "config/api_keys.json.tmp",
                         "config/api_keys.json.broken-1790000000",
                         "memory/long_term.json",
                         "memory/long_term.json.bak-1790000000"):
                (repo / name).write_text("{}", encoding="utf-8")
            for name in ("config/api_keys.json.tmp",
                         "config/api_keys.json.broken-1790000000",
                         "memory/long_term.json.bak-1790000000"):
                r = subprocess.run([git, "check-ignore", "-q", name], cwd=repo)
                self.assertEqual(r.returncode, 0, f"{name} is NOT ignored")


class LinuxFirewallTests(unittest.TestCase):
    """The Linux branch of the dashboard's firewall helper used an undefined name.

    `_ensure_network_access(*ports)` referred to a bare `port` nine times, so on
    any Linux machine with ufw, firewalld or iptables actually running it raised
    NameError — in a background thread, inside a best-effort call, which is the
    shape of bug that never says anything and simply leaves the phone unable to
    reach the dashboard.
    """

    def setUp(self):
        if not sys.platform.startswith("linux"):
            raise unittest.SkipTest("this is the Linux branch")
        import importlib
        self.server = importlib.import_module("dashboard.server")

    def _run_with(self, stdout: str, returncode: int = 0):
        """Call the helper with a fake subprocess, and record what it ran."""
        import types
        called = []

        class Result:
            def __init__(self):
                self.stdout = stdout
                self.stderr = ""
                self.returncode = returncode

        def run(cmd, **_kwargs):          # noqa: ANN001 - mirrors subprocess.run
            called.append(list(cmd))
            if cmd[:2] == ["ufw", "status"]:
                return Result()
            if cmd[:2] == ["pkexec", "ufw"]:
                return Result()
            return Result()

        fake = types.SimpleNamespace(run=run, PIPE=-1, DEVNULL=-2,
                                     CalledProcessError=Exception)
        real = sys.modules.get("subprocess")
        sys.modules["subprocess"] = fake
        try:
            self.server._ensure_network_access(8000, 8001)
        finally:
            if real is not None:
                sys.modules["subprocess"] = real
        return called

    def test_every_port_is_opened_and_nothing_raises(self):
        called = self._run_with("Status: active")
        allowed = [c for c in called if c[:2] == ["pkexec", "ufw"]]
        self.assertEqual(len(allowed), 2, called)
        self.assertIn("8000/tcp", allowed[0])
        self.assertIn("8001/tcp", allowed[1])

    def test_an_inactive_ufw_is_skipped_and_the_next_tool_is_tried(self):
        called = self._run_with("Status: inactive")
        self.assertEqual([c for c in called if c[:3] == ["pkexec", "ufw", "allow"]], [])
        self.assertEqual([c for c in called if "--add-port" in c], [],
                         "an inactive ufw must not lead to a firewalld rule either")
        # iptables answers here, so it is the fallback that gets the work.
        ipt = [c for c in called if c[:2] == ["pkexec", "iptables"]]
        self.assertEqual(len(ipt), 2, called)


if __name__ == "__main__":
    unittest.main()
