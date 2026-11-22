"""Model-supplied text must not be able to leave an AppleScript string (macOS paths).

`actions/computer_control.py::_focus_window` and `actions/desktop.py::_apply_wallpaper` built
the program given to `osascript -e` with an f-string around text the model chose. The Windows
branch of `_focus_window` was already quoted for PowerShell; the macOS branch beside it was
not, so a window title could end the string and run `do shell script`. The same function also
said "Focused window" whatever the answer was, on all three platforms.
"""

from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from actions import computer_control, desktop
from core import applescript

INJECTION = 'x") to true\ndo shell script "touch /tmp/pwned"\n(first process whose name contains "y'


def string_literals(script: str):
    """The contents of each double-quoted literal in a script, honouring backslash escapes."""
    found, inside, current, escaped = [], False, [], False
    for char in script:
        if not inside:
            if char == '"':
                inside, current = True, []
            continue
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
            current.append(char)
        elif char == '"':
            found.append("".join(current))
            inside = False
        else:
            current.append(char)
    return found, inside


class Quoting(unittest.TestCase):
    def test_quotes_and_backslashes_are_escaped_and_nothing_else_is(self):
        self.assertEqual(applescript.quote('a"b\\c'), 'a\\"b\\\\c')
        self.assertEqual(applescript.quote("plain text, ünïcode 1+1 $x `y`"),
                         "plain text, ünïcode 1+1 $x `y`")
        self.assertEqual(applescript.literal("a"), '"a"')

    def test_a_null_byte_is_dropped_rather_than_crashing_argv(self):
        self.assertEqual(applescript.quote("a\x00b"), "ab")

    def test_whatever_is_quoted_stays_inside_one_literal(self):
        for text in (INJECTION, '"', "\\", '\\"', '"\\', "a\\\\\"b", "'; rm -rf ~; '",
                     "line one\nline two", ""):
            with self.subTest(text=text):
                script = f'tell app "X" to activate (name contains {applescript.literal(text)}) end'
                literals, unterminated = string_literals(script)
                self.assertFalse(unterminated)
                self.assertEqual(literals, ["X", applescript.quote(text)])


class FocusWindow(unittest.TestCase):
    def run_on(self, os_name, completed=None, title="Notes"):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            return completed if completed is not None else subprocess.CompletedProcess(
                command, 0, b"True\r\n", b"")

        with mock.patch.object(computer_control, "_get_os", return_value=os_name), \
                mock.patch.object(computer_control.subprocess, "run", fake_run), \
                mock.patch.object(computer_control.time, "sleep"):
            return computer_control._focus_window(title), calls

    def test_the_mac_script_keeps_a_hostile_title_inside_its_string(self):
        _said, calls = self.run_on("mac", title=INJECTION)
        script = calls[0][calls[0].index("-e") + 1]
        literals, unterminated = string_literals(script)
        self.assertFalse(unterminated)
        self.assertEqual(literals, ["System Events", applescript.quote(INJECTION)])
        self.assertNotIn('do shell script "touch', script.replace(applescript.quote(INJECTION), ""))

    def test_an_ordinary_mac_title_is_unchanged(self):
        said, calls = self.run_on("mac", title="Safari")
        self.assertIn('contains "Safari"', calls[0][-1])
        self.assertEqual(said, "Focused window: Safari")

    def test_mac_does_not_claim_focus_when_osascript_failed(self):
        said, _calls = self.run_on("mac", subprocess.CompletedProcess(
            ["osascript"], 1, b"", b"Can't get process whose name contains \"Nope\"."), title="Nope")
        self.assertNotIn("Focused window", said)
        self.assertIn("Can't get process", said)

    def test_windows_does_not_claim_focus_when_no_window_matched(self):
        said, _calls = self.run_on("windows", subprocess.CompletedProcess(
            ["powershell"], 0, b"False\r\n", b""), title="Nothing here")
        self.assertNotIn("Focused window", said)
        self.assertIn("Nothing here", said)

    def test_windows_claims_focus_only_when_appactivate_said_true(self):
        said, _calls = self.run_on("windows", title="Notepad")
        self.assertEqual(said, "Focused window: Notepad")

    def test_windows_title_with_a_quote_stays_one_powershell_string(self):
        _said, calls = self.run_on("windows", title="it's a 'trap'")
        self.assertIn("AppActivate('it''s a ''trap''')", calls[0][-1])

    def test_linux_xdotool_failure_is_not_reported_as_focus(self):
        def fake_run(command, **kwargs):
            if command[0] == "wmctrl":
                raise FileNotFoundError
            return subprocess.CompletedProcess(command, 1, b"", b"")

        with mock.patch.object(computer_control, "_get_os", return_value="linux"), \
                mock.patch.object(computer_control.subprocess, "run", fake_run), \
                mock.patch.object(computer_control.time, "sleep"):
            said = computer_control._focus_window("Nope")
        self.assertNotIn("Focused window", said)
        self.assertIn("no window matched", said)

    def test_linux_wmctrl_success_is_reported(self):
        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, b"", b"")

        with mock.patch.object(computer_control, "_get_os", return_value="linux"), \
                mock.patch.object(computer_control.subprocess, "run", fake_run), \
                mock.patch.object(computer_control.time, "sleep"):
            self.assertEqual(computer_control._focus_window("Files"), "Focused window: Files")


class WallpaperScript(unittest.TestCase):
    def test_a_path_with_a_quote_cannot_end_the_applescript_string(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / 'a" & (do shell script "id") & ".png'
            try:
                image.write_bytes(b"\x89PNG")
            except OSError:
                # Windows does not allow a double quote in a file name, so this path cannot
                # exist there (the first Windows run: "Invalid argument"). Nothing is lost by
                # skipping: the quoting is tested above on the same hostile text with no file.
                self.skipTest("this file system cannot hold a file name with a double quote")
            seen = []

            def fake_run(command, **kwargs):
                seen.append(command)
                return subprocess.CompletedProcess(command, 0, b"", b"")

            with mock.patch.object(desktop, "_OS", "Darwin"), \
                    mock.patch.object(desktop.subprocess, "run", fake_run):
                desktop._apply_wallpaper(str(image))
        script = seen[0][seen[0].index("-e") + 1]
        literals, unterminated = string_literals(script)
        self.assertFalse(unterminated)
        self.assertEqual(len(literals), 2, script)    # "System Events" and the one path
        self.assertIn("do shell script", literals[1], "the payload is data inside the literal")


if __name__ == "__main__":
    unittest.main()
