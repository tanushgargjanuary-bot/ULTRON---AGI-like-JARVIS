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

    def test_windows_drive_resolution_and_critical_protection(self):
        with patch.object(file_controller, "_OS", "Windows"):
            resolved_d = file_controller._resolve_path("d:")
            self.assertEqual(resolved_d, Path("D:/"))

            sub_d = file_controller._resolve_path("d:projects/app.py")
            self.assertEqual(sub_d, Path("D:/projects/app.py"))

            # Critical OS system directory protection
            sys32 = Path("C:/Windows/System32/cmd.exe")
            self.assertTrue(file_controller._is_sensitive(sys32))
            self.assertFalse(file_controller._is_safe_path(sys32))
            self.assertIn("critical operating system", file_controller._denial_message(sys32))


if __name__ == "__main__":
    unittest.main()
