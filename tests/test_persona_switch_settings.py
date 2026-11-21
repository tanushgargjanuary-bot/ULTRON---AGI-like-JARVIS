"""Switching persona or theme: what is saved, what is kept, and what the window says.

`MainWindow._select_persona_theme` changes the assistant's identity and look. Its save moved to
`memory.config_manager.save_settings_strict` (see `test_ui_settings_writes.py`), and the lines
before the save that filled in a dictionary for the old whole-file write stayed behind: six
stores into `data[...]` that nothing read, which made it look as if the method still wrote that
dictionary. They are gone. There was no test of the switch itself, so these add one: the method
is called on a stand-in for the window, against a scratch settings file, with the colour-applying
functions replaced (they change process-wide palette state and need real widgets).

A test that needs Qt is skipped on a machine without it, like the neighbouring ones.
"""

from __future__ import annotations

import ast
import types
import unittest
from pathlib import Path
from unittest import mock

try:
    from tempconfig import WithATemporaryConfig, cm
except ImportError:                       # imported as tests.test_persona_switch_settings
    from tests.tempconfig import WithATemporaryConfig, cm

ROOT = Path(__file__).resolve().parents[1]
SECRETS = {
    "gemini_api_key": "FIXTURE-KEY-keep-me",
    "providers": {"creds": {"openai_compat@groq": {"api_key": "FIXTURE-groq-keep-me"}}},
    "ui_scale": 1.25,
}


class TheMethodStoresNothingItNeverReads(unittest.TestCase):
    """Source-level, so it runs with no Qt."""

    def method(self) -> ast.FunctionDef:
        tree = ast.parse((ROOT / "ui.py").read_text(encoding="utf-8"))
        found = [node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef) and node.name == "_select_persona_theme"]
        self.assertEqual(len(found), 1)
        return found[0]

    def test_it_makes_no_assignment_into_the_snapshot_dictionary(self):
        stores = [node.lineno for node in ast.walk(self.method())
                  if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store)
                  and isinstance(node.value, ast.Name) and node.value.id == "data"]
        self.assertEqual(stores, [], "values are stored into `data` and nothing reads them back "
                                     "(the save goes through `save_settings_strict(**chosen)`)")

    def test_it_still_saves_through_the_settings_module(self):
        names = {node.func.id for node in ast.walk(self.method())
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertIn("save_settings_strict", names)

    def test_it_does_not_write_a_file_itself(self):
        # Calls, not words: a comment in the method explains why it does not use write_text.
        writes = [node.lineno for node in ast.walk(self.method())
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr in ("write_text", "write_bytes", "write")]
        self.assertEqual(writes, [])


class TheSwitch(WithATemporaryConfig):
    def setUp(self):
        super().setUp()
        try:
            import ui
        except Exception as error:               # no Qt on this machine
            self.skipTest(f"ui.py cannot be imported here: {error}")
        self.ui = ui
        for name in ("apply_ui_theme", "apply_ui_accent", "retheme_all_widgets", "current_palette"):
            patcher = mock.patch.object(ui, name, mock.Mock(return_value=None))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(ui, "API_FILE", cm.CONFIG_FILE)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.lines: list[str] = []
        self.voice_changes = mock.Mock()
        self.window = types.SimpleNamespace(
            _persona_id="ultron",
            _assistant_name="Ultron",
            setWindowTitle=lambda *_: None,
            _title_lbl=types.SimpleNamespace(setText=lambda *_: None),
            _sub_lbl=types.SimpleNamespace(setText=lambda *_: None),
            _log=types.SimpleNamespace(append_log=self.lines.append, _ai_name_lc=""),
            hud=types.SimpleNamespace(_assistant_name="", _avatar=None),
            on_voice_change=self.voice_changes,
        )

    def switch(self, persona="hacker", theme="violet_nebula"):
        self.ui.MainWindow._select_persona_theme(self.window, persona, theme)

    def test_the_choice_is_saved_and_every_other_key_is_kept(self):
        self.write_settings(SECRETS)
        self.switch("hacker", "violet_nebula")
        after = self.read_settings()
        self.assertEqual(after["persona_id"], "hacker")
        self.assertEqual(after["ui_theme"], "violet_nebula")
        self.assertEqual(after["ui_color"], "#a47bff")
        self.assertEqual(after["voice_name"], "Fenrir", "the persona's own voice, none being remembered")
        self.assertEqual(after["gemini_api_key"], SECRETS["gemini_api_key"])
        self.assertEqual(after["providers"], SECRETS["providers"])
        self.assertEqual(after["ui_scale"], 1.25)

    def test_the_outgoing_voice_is_remembered_and_comes_back_on_return(self):
        self.write_settings(dict(SECRETS, voice_name="Kore"))
        self.switch("hacker", "violet_nebula")
        voices = self.read_settings()["persona_voices"]
        self.assertEqual(voices["ultron"], "Kore", "the voice in use was not remembered for a later return")
        self.assertEqual(voices["hacker"], "Fenrir")
        self.switch("ultron", "classic_cyan")
        self.assertEqual(self.read_settings()["voice_name"], "Kore")

    def test_going_to_ultron_names_the_assistant_ultron(self):
        self.write_settings(dict(SECRETS, assistant_name="Cipher"))
        self.window._persona_id = "hacker"
        self.switch("ultron", "classic_cyan")
        self.assertEqual(self.read_settings()["assistant_name"], "Ultron")

    def test_going_to_another_persona_leaves_the_assistant_name_to_the_persona(self):
        self.write_settings(dict(SECRETS, assistant_name="Zed"))
        self.switch("hacker", "violet_nebula")
        self.assertEqual(self.read_settings()["assistant_name"], "Zed", "this method does not rename")
        self.assertEqual(self.window._assistant_name, "Cipher")

    def test_the_window_says_what_changed(self):
        self.write_settings(SECRETS)
        self.switch("hacker", "violet_nebula")
        self.assertTrue(any(line.startswith("SYS: Switched to Cipher") and "Violet Nebula" in line
                            for line in self.lines), self.lines)
        self.assertTrue(any("Voice set" in line and "Fenrir" in line for line in self.lines), self.lines)

    def test_a_changed_voice_tells_the_session_to_restart_its_voice(self):
        self.write_settings(SECRETS)
        self.switch("hacker", "violet_nebula")
        self.voice_changes.assert_called_once()

    def test_the_same_persona_and_voice_changes_nothing_for_the_session(self):
        self.write_settings(SECRETS)
        self.switch("ultron", "amber_arc")
        self.voice_changes.assert_not_called()
        self.assertEqual(self.read_settings()["ui_theme"], "amber_arc")

    def test_an_unknown_theme_changes_nothing(self):
        self.write_settings(SECRETS)
        before = cm.CONFIG_FILE.read_bytes()
        self.switch("hacker", "not-a-theme")
        self.assertEqual(cm.CONFIG_FILE.read_bytes(), before)
        self.assertEqual(self.lines, [])

    def test_a_custom_theme_uses_the_saved_colour_and_refuses_a_bad_one(self):
        self.write_settings(dict(SECRETS, ui_color="#123abc"))
        self.switch("ultron", "custom")
        self.assertEqual(self.read_settings()["ui_color"], "#123abc")
        self.write_settings(dict(SECRETS, ui_color="#12zzzz"))
        before = cm.CONFIG_FILE.read_bytes()
        self.lines.clear()
        self.switch("hacker", "custom")
        self.assertEqual(cm.CONFIG_FILE.read_bytes(), before)
        self.assertEqual(self.lines, [])

    def test_a_save_that_fails_is_reported_and_not_called_a_switch(self):
        self.write_settings(SECRETS)
        with mock.patch.object(cm, "save_settings_strict", side_effect=OSError("disk is full")):
            self.switch("hacker", "violet_nebula")
        self.assertTrue(any(line.startswith("ERR: Could not save persona selection") for line in self.lines),
                        self.lines)
        self.assertFalse(any(line.startswith("SYS: Switched") for line in self.lines), self.lines)

    def test_a_failed_read_of_the_snapshot_still_cannot_cost_the_owner_a_key(self):
        # The old whole-file write turned an unreadable file into {} and wrote the three new keys over
        # everything. The save now merges into what is on disk, so the snapshot cannot do that.
        self.write_settings(SECRETS)
        with mock.patch.object(self.ui, "_read_full_config", return_value={}):
            self.switch("hacker", "violet_nebula")
        after = self.read_settings()
        self.assertEqual(after["gemini_api_key"], SECRETS["gemini_api_key"])
        self.assertEqual(after["providers"], SECRETS["providers"])
        self.assertEqual(after["persona_id"], "hacker")


if __name__ == "__main__":
    unittest.main()
