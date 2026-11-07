"""tests/test_ocr.py — Unit tests for local OCR extraction rung."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from core import ocr


class OcrEngineTests(unittest.TestCase):
    def test_ocr_available_returns_valid_tuple(self):
        usable, engine = ocr.ocr_available()
        self.assertIsInstance(usable, bool)
        self.assertIsInstance(engine, str)

    def test_extract_words_returns_empty_when_unavailable(self):
        with patch.object(ocr, "ocr_available", return_value=(False, "none")):
            words = ocr.extract_words("dummy_path.png")
            self.assertEqual(words, [])

    def test_extract_words_pytesseract_parsing(self):
        mock_data = {
            "text": ["", "Save", "Cancel", ""],
            "left": [0, 10, 50, 100],
            "top": [0, 20, 20, 100],
            "width": [0, 30, 40, 0],
            "height": [0, 15, 15, 0],
        }
        with patch.object(ocr, "ocr_available", return_value=(True, "pytesseract")):
            with patch("core.ocr._extract_pytesseract", return_value=[
                {"text": "Save", "x": 10, "y": 20, "w": 30, "h": 15},
                {"text": "Cancel", "x": 50, "y": 20, "w": 40, "h": 15},
            ]):
                words = ocr.extract_words("dummy.png")
                self.assertEqual(len(words), 2)
                self.assertEqual(words[0]["text"], "Save")
                self.assertEqual(words[1]["text"], "Cancel")

    def test_extract_words_easyocr_parsing(self):
        raw_result = [
            ([ [10, 10], [50, 10], [50, 30], [10, 30] ], "OK", 0.99),
        ]
        with patch.object(ocr, "ocr_available", return_value=(True, "easyocr")):
            with patch("core.ocr._extract_easyocr", return_value=[
                {"text": "OK", "x": 10, "y": 10, "w": 40, "h": 20},
            ]):
                words = ocr.extract_words("dummy.png")
                self.assertEqual(len(words), 1)
                self.assertEqual(words[0]["text"], "OK")

    def test_extract_words_catches_and_notes_failure(self):
        with patch.object(ocr, "ocr_available", return_value=(True, "pytesseract")):
            with patch("core.ocr._extract_pytesseract", side_effect=RuntimeError("OCR crash")):
                words = ocr.extract_words("dummy.png")
                self.assertEqual(words, [])


if __name__ == "__main__":
    unittest.main()

