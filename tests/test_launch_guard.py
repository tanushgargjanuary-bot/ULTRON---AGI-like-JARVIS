"""The startup refusal must be a sentence a person can act on.

These tests never import ``main.py``: the repository rule is that importing the entry point
starts a window and installs crash hooks. The guard lives in its own module so the words and
the decision can be checked on their own.
"""

import unittest
from unittest.mock import patch

from core import launch_guard


class TheVersionCheck(unittest.TestCase):
    def test_the_supported_versions_are_3_11_to_3_13(self):
        for version in ((3, 11), (3, 12), (3, 13)):
            self.assertTrue(launch_guard.supported(version), version)

    def test_3_14_is_refused(self):
        self.assertFalse(launch_guard.supported((3, 14)))

    def test_an_old_python_is_refused(self):
        self.assertFalse(launch_guard.supported((3, 9)))

    def test_a_longer_version_tuple_still_matches(self):
        self.assertTrue(launch_guard.supported((3, 12, 4, "final", 0)))


class TheWords(unittest.TestCase):
    """Every refusal names both commands that work."""

    def test_the_version_message_names_the_python_and_both_commands(self):
        message = launch_guard.version_message((3, 14, 0))
        self.assertIn("3.14", message)
        self.assertIn("run.bat", message)
        self.assertIn(".venv\\Scripts\\python.exe main.py", message)

    def test_the_package_message_names_the_package_and_the_folder(self):
        message = launch_guard.missing_package_message("PyQt6")
        self.assertIn("PyQt6", message)
        self.assertIn(".venv", message)
        self.assertIn("run.bat", message)

    def test_no_message_is_a_traceback(self):
        for message in (
            launch_guard.version_message((3, 14, 0)),
            launch_guard.missing_package_message(),
        ):
            self.assertNotIn("Traceback", message)


class TheRefusal(unittest.TestCase):
    def test_a_wrong_version_stops_before_the_heavy_imports(self):
        with self.assertRaises(SystemExit) as caught:
            launch_guard.stop_early(version=(3, 14, 0), has_package=True)
        # The reason is the exit value: Python prints it and no traceback follows.
        self.assertIn("3.14", str(caught.exception.code))

    def test_a_missing_package_stops_with_the_folder_message(self):
        with self.assertRaises(SystemExit) as caught:
            launch_guard.stop_early(version=(3, 12, 0), has_package=False)
        self.assertIn("PyQt6", str(caught.exception.code))

    def test_nothing_is_printed_from_the_library(self):
        with patch("builtins.print") as printed:
            with self.assertRaises(SystemExit):
                launch_guard.stop_early(version=(3, 14, 0), has_package=True)
        printed.assert_not_called()

    def test_a_good_interpreter_with_the_package_continues(self):
        self.assertIsNone(launch_guard.stop_early(version=(3, 12, 0), has_package=True))


if __name__ == "__main__":
    unittest.main()
