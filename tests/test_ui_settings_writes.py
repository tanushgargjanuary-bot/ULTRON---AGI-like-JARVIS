"""The window must save identity and persona choices through the settings module.

`ui.py` had two places that changed settings (switching persona/theme, and editing the
assistant's name, the user's name, colour and voice) which did this:

    data = _read_full_config()      # {} on ANY read error
    data[...] = ...
    API_FILE.write_text(json.dumps(data, indent=4))     # then said "Switched" / "updated"

`AGENTS.md` says never to write that file directly, and this is why: when the read failed for
a moment (another program had the file open) `data` was `{}`, and the write replaced every
key, including the Gemini key and the providers, with the three it had just been given. It also
wrote outside the settings lock, from a snapshot, and announced the change whether or not it
had been saved. They now call `memory.config_manager.save_settings_strict`.
"""

from __future__ import annotations

import ast
import types
import unittest
from pathlib import Path
from unittest import mock

try:
    from tempconfig import WithATemporaryConfig, cm
except ImportError:                       # imported as tests.test_ui_settings_writes
    from tests.tempconfig import WithATemporaryConfig, cm

ROOT = Path(__file__).resolve().parents[1]
SECRETS = {
    "gemini_api_key": "AIza-REAL-KEY-0123456789",
    "providers": {"creds": {"openai_compat@groq": {"api_key": "sk-keep-me"}}},
    "ui_scale": 1.25,
}


class SaveSettingsStrict(WithATemporaryConfig):
    def test_it_changes_named_keys_and_keeps_every_other(self):
        self.write_settings(dict(SECRETS, assistant_name="Old"))
        cm.save_settings_strict(assistant_name="Nova", user_name="Asha")
        after = self.read_settings()
        self.assertEqual(after["assistant_name"], "Nova")
        self.assertEqual(after["user_name"], "Asha")
        self.assertEqual(after["gemini_api_key"], SECRETS["gemini_api_key"])
        self.assertEqual(after["providers"], SECRETS["providers"])
        self.assertEqual(after["ui_scale"], 1.25)

    def test_a_file_that_cannot_be_read_is_not_overwritten_and_it_raises(self):
        self.write_settings(SECRETS)
        before = cm.CONFIG_FILE.read_bytes()
        real = Path.read_bytes

        def locked(path, *args, **kwargs):
            if path == cm.CONFIG_FILE:
                raise PermissionError("another program has it open")
            return real(path, *args, **kwargs)

        with mock.patch.object(Path, "read_bytes", locked):
            with self.assertRaises(OSError):
                cm.save_settings_strict(assistant_name="Nova")
        self.assertEqual(cm.CONFIG_FILE.read_bytes(), before)

    def test_a_write_that_fails_raises_instead_of_returning_quietly(self):
        self.write_settings(SECRETS)
        with mock.patch.object(cm.os, "replace", side_effect=OSError("disk full")), \
                mock.patch.object(cm.time, "sleep"):
            with self.assertRaises(OSError):
                cm.save_settings_strict(assistant_name="Nova")
        self.assertEqual(self.read_settings()["gemini_api_key"], SECRETS["gemini_api_key"])


class TheWindowDoesNotWriteTheFileItself(unittest.TestCase):
    def test_ui_never_calls_write_text_on_the_settings_path(self):
        tree = ast.parse((ROOT / "ui.py").read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "write_text"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "API_FILE"):
                offenders.append(node.lineno)
        self.assertEqual(offenders, [], "ui.py writes api_keys.json itself, at these lines")


class TheIdentityUpdate(WithATemporaryConfig):
    """`MainWindow._apply_name_update`, called on a stand-in for the window."""

    def setUp(self):
        super().setUp()
        try:
            import ui
        except Exception as error:               # no Qt on this machine
            self.skipTest(f"ui.py cannot be imported here: {error}")
        self.ui = ui
        patcher = mock.patch.object(ui, "API_FILE", cm.CONFIG_FILE)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.lines = []
        self.window = types.SimpleNamespace(
            setWindowTitle=lambda *_: None,
            _title_lbl=types.SimpleNamespace(setText=lambda *_: None),
            _sub_lbl=types.SimpleNamespace(setText=lambda *_: None),
            _log=types.SimpleNamespace(append_log=self.lines.append, _ai_name_lc=""),
            hud=types.SimpleNamespace(_assistant_name=""),
            _persona_id="ultron",
        )

    def update(self, name="Nova", user="Asha", **kw):
        self.ui.MainWindow._apply_name_update(self.window, name, user, **kw)

    def test_a_normal_update_changes_the_names_and_keeps_the_keys(self):
        self.write_settings(SECRETS)
        self.update()
        after = self.read_settings()
        self.assertEqual((after["assistant_name"], after["user_name"]), ("Nova", "Asha"))
        self.assertEqual(after["gemini_api_key"], SECRETS["gemini_api_key"])
        self.assertTrue(any("Identity updated" in line for line in self.lines), self.lines)

    def test_an_unreadable_file_keeps_the_keys_and_the_window_says_it_failed(self):
        self.write_settings(SECRETS)
        before = cm.CONFIG_FILE.read_bytes()
        real_bytes, real_text = Path.read_bytes, Path.read_text

        def locked_bytes(path, *a, **k):
            if path == cm.CONFIG_FILE:
                raise PermissionError("another program has it open")
            return real_bytes(path, *a, **k)

        def locked_text(path, *a, **k):
            if path == cm.CONFIG_FILE:
                raise PermissionError("another program has it open")
            return real_text(path, *a, **k)

        with mock.patch.object(Path, "read_bytes", locked_bytes), \
                mock.patch.object(Path, "read_text", locked_text):
            self.update()
        self.assertEqual(cm.CONFIG_FILE.read_bytes(), before, "nothing was overwritten")
        self.assertFalse(any("Identity updated" in line for line in self.lines), self.lines)
        self.assertTrue(any(line.startswith("ERR: Config save failed") for line in self.lines),
                        self.lines)


if __name__ == "__main__":
    unittest.main()
