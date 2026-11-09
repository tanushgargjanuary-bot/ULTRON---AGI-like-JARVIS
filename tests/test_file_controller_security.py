"""Platform-specific path safety regressions for the file controller."""

import unittest
from pathlib import Path
from unittest.mock import patch

from actions import file_controller


class FileControllerPathSafetyTests(unittest.TestCase):
    def test_windows_alternate_data_stream_names_are_refused(self):
        target = Path.home() / "Documents" / "report.txt:secret"
        with patch.object(file_controller, "_OS", "Windows"):
            self.assertFalse(file_controller._is_safe_path(target))

    def test_colons_remain_valid_in_non_windows_file_names(self):
        target = Path.home() / "Documents" / "report:notes.txt"
        with patch.object(file_controller, "_OS", "Linux"):
            with patch.object(file_controller, "_SAFE_ROOTS", [Path.home()]):
                self.assertTrue(file_controller._is_safe_path(target))


if __name__ == "__main__":
    unittest.main()
