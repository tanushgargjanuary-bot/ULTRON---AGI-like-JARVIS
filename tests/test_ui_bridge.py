"""The accessibility bridge must never advertise a backend it cannot drive.

This is the file that exists because of a real defect: `available()` used to
answer "yes, pywinauto" whenever pywinauto was importable — and pywinauto IS
importable on every Windows install, because three plugins import it directly.
So on a clean machine the app told the tool ladder "the accessibility tree
works", the ladder preferred it over vision exactly as the user asked, and the
first real action raised `pywinauto fallback is not implemented`. The user would
have seen the one capability the whole design is built around fail on the first
attempt, with a message about a package they had never heard of.

The bridge itself still cannot be exercised without Windows — that is what
`scripts/verify_windows.py` is for. What is testable here, everywhere, is the
promise: `usable` is true only when a driver exists AND its package is installed.
"""

from __future__ import annotations

import platform
import unittest
from pathlib import Path
from unittest import mock

from core import ui_windows

ROOT = Path(__file__).resolve().parents[1]


class AvailabilityTests(unittest.TestCase):
    def _ask(self, system: str, installed: set[str]):
        with mock.patch.object(ui_windows.platform, "system", return_value=system), \
             mock.patch.object(ui_windows, "_importable",
                               side_effect=lambda name: name in installed):
            return ui_windows.available()

    def test_other_platforms_say_which_platform(self):
        usable, reason = self._ask("Linux", {"uiautomation", "pywinauto"})
        self.assertFalse(usable)
        self.assertIn("Linux", reason)

    def test_windows_with_the_implemented_backend_is_usable(self):
        usable, reason = self._ask("Windows", {"uiautomation"})
        self.assertTrue(usable)
        self.assertEqual(reason, "uiautomation")

    def test_windows_with_nothing_says_what_to_install(self):
        usable, reason = self._ask("Windows", set())
        self.assertFalse(usable)
        self.assertIn("uiautomation", reason)

    def test_pywinauto_alone_is_not_usable(self):
        """The regression. pywinauto installed, uiautomation missing."""
        usable, reason = self._ask("Windows", {"pywinauto"})
        self.assertFalse(usable, "pywinauto has no driver — this must not read as usable")
        self.assertIn("pywinauto", reason)
        self.assertIn("uiautomation", reason, "the reason must name the package to install")

    def test_pywinauto_alone_is_still_reported_truthfully(self):
        """Not usable, but the message must not pretend nothing is installed."""
        _usable, reason = self._ask("Windows", {"pywinauto"})
        self.assertIn("installed", reason)


class AdapterHonestyTests(unittest.TestCase):
    def test_capabilities_never_claim_a_tree_that_cannot_be_walked(self):
        with mock.patch.object(ui_windows.platform, "system", return_value="Windows"), \
             mock.patch.object(ui_windows, "_importable",
                               side_effect=lambda name: name == "pywinauto"):
            adapter = ui_windows.WindowsAdapter()
            self.assertNotIn("uia", adapter.capabilities())

    def test_a_backend_without_a_driver_fails_loudly_not_silently(self):
        """Belt and braces: if available() ever regresses, _module() must raise
        a RuntimeError that names the problem, not an ImportError."""
        with mock.patch.object(ui_windows, "available", return_value=(True, "pywinauto")):
            adapter = ui_windows.WindowsAdapter()
            with self.assertRaises(RuntimeError) as caught:
                adapter._module()
        self.assertIn("uiautomation", str(caught.exception))


class DeclaredDependencyTests(unittest.TestCase):
    def test_the_implemented_backend_is_a_declared_dependency(self):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        windows_lines = [line for line in text.splitlines()
                         if "sys_platform" in line and "win32" in line]
        self.assertTrue(any(line.strip().startswith("uiautomation")
                            for line in windows_lines),
                        "uiautomation must be installed on Windows, or the bridge "
                        "cannot run at all")
        self.assertTrue(any(line.strip().startswith("pywinauto")
                            for line in windows_lines),
                        "the three plugins import pywinauto directly")

    def test_the_bridge_docstring_still_says_what_is_unverified(self):
        """The module promises not to be described as working on Windows until it
        has run there. Keep that sentence where the next reader will find it."""
        source = (ROOT / "core" / "ui_windows.py").read_text(encoding="utf-8")
        self.assertIn("unverified", source.lower())


if __name__ == "__main__":
    unittest.main()
