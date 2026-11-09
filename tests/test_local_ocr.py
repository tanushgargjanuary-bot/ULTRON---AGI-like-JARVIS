"""Tests for on-device text reading from images."""

import unittest
from pathlib import Path

from core.local_ocr import MAX_IMAGE_BYTES, available, extract_text


class _Image:
    width = 8
    height = 8

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def verify(self):
        return None

    def convert(self, _mode):
        return self


class _ImageModule:
    @staticmethod
    def open(_stream):
        return _Image()


class LocalOcrTests(unittest.TestCase):
    def test_ocr_uses_injected_local_engine_and_cleans_output(self):
        seen = []

        def engine(image, **kwargs):
            seen.append((image, kwargs))
            return "Save  \n\n Cancel\n"

        result = extract_text(b"fixture-bytes", ocr_engine=engine,
                              image_module=_ImageModule)
        self.assertEqual(result, "Save\n\n Cancel")
        self.assertEqual(seen[0][1]["config"], "--psm 6")
        self.assertEqual(seen[0][1]["timeout"], 15)

    def test_oversized_images_are_refused_before_decode(self):
        with self.assertRaisesRegex(ValueError, "8 MB"):
            extract_text(b"x" * (MAX_IMAGE_BYTES + 1), image_module=_ImageModule)

    def test_empty_input_is_refused(self):
        with self.assertRaisesRegex(ValueError, "non-empty"):
            extract_text(b"", image_module=_ImageModule)

    @unittest.skipUnless(available(), "optional Pillow, pytesseract, and Tesseract are required")
    def test_known_fixture_is_recognized_by_local_tesseract(self):
        fixture = Path(__file__).parent / "fixtures" / "ocr_ok.bmp"
        text = extract_text(fixture.read_bytes())
        self.assertIn("OK", text.upper())


if __name__ == "__main__":
    unittest.main()
