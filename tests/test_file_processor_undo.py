"""Tests that processed files can be restored with undo."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import file_processor
from core import undo


class FileProcessorOutputUndoTests(unittest.TestCase):
    def setUp(self):
        undo.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def tearDown(self):
        undo.clear()

    def test_undo_removes_new_generated_text_output(self):
        output = self.root / "summary.txt"
        file_processor._write_text_output(output, "generated summary")

        self.assertEqual(output.read_text(encoding="utf-8"), "generated summary")
        self.assertIn("summary.txt", undo.peek())
        self.assertTrue(undo.undo_last().startswith("Undone:"))
        self.assertFalse(output.exists())

    def test_undo_restores_existing_file_byte_for_byte(self):
        output = self.root / "summary.txt"
        original = b"old text\r\nwith legacy bytes\xff"
        output.write_bytes(original)

        file_processor._write_text_output(output, "replacement")
        self.assertEqual(output.read_text(encoding="utf-8"), "replacement")
        self.assertTrue(undo.undo_last().startswith("Undone:"))
        self.assertEqual(output.read_bytes(), original)

    def test_undo_refuses_to_clobber_output_changed_after_creation(self):
        output = self.root / "summary.txt"
        file_processor._write_text_output(output, "generated")
        output.write_text("user edit", encoding="utf-8")

        result = undo.undo_last()
        self.assertIn("output changed after creation", result)
        self.assertEqual(output.read_text(encoding="utf-8"), "user edit")

    def test_large_existing_output_is_not_overwritten(self):
        output = self.root / "large.txt"
        original = b"x" * (file_processor._MAX_UNDO_SNAPSHOT + 1)
        output.write_bytes(original)

        with self.assertRaisesRegex(ValueError, "safe undo limit"):
            file_processor._write_text_output(output, "replacement")
        self.assertEqual(output.read_bytes(), original)
        self.assertFalse(undo.can_undo())

    def test_failed_undo_registration_rolls_back_new_output(self):
        output = self.root / "summary.txt"
        with patch.object(file_processor, "push_undo", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "rolled back"):
                file_processor._write_text_output(output, "generated")
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
