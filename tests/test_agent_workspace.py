"""Tests for the read-only agent workspace report helpers."""
import unittest

from scripts.agent_workspace import _parse_name_status


class NameStatusTests(unittest.TestCase):
    def test_added_modified_deleted_and_paths_with_spaces(self):
        raw = "A\0new file.py\0M\0old file.py\0D\0gone.py\0"
        self.assertEqual(_parse_name_status(raw), [
            ("A", "new file.py", None),
            ("M", "old file.py", None),
            ("D", "gone.py", None),
        ])

    def test_rename_contains_both_paths(self):
        raw = "R100\0old name.py\0new name.py\0"
        self.assertEqual(_parse_name_status(raw), [("R100", "old name.py", "new name.py")])

    def test_empty_and_truncated_output(self):
        self.assertEqual(_parse_name_status(""), [])
        self.assertEqual(_parse_name_status("M\0"), [])


if __name__ == "__main__":
    unittest.main()
