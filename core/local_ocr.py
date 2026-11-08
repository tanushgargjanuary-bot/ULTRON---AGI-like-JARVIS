"""Optional local-only OCR. This module never opens a network connection."""

from __future__ import annotations

import importlib.util
import io
import shutil

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_TEXT_CHARS = 12_000


def available() -> bool:
    """True only when both the Python wrapper and local Tesseract binary exist."""
    try:
        return (importlib.util.find_spec("PIL") is not None
                and importlib.util.find_spec("pytesseract") is not None
                and shutil.which("tesseract") is not None)
    except (ImportError, ValueError):
        return False


def unavailable_reason() -> str:
    if importlib.util.find_spec("PIL") is None:
        return "Pillow is missing; install the optional OCR extra"
    if importlib.util.find_spec("pytesseract") is None:
        return "pytesseract is missing; install the optional OCR extra"
    if shutil.which("tesseract") is None:
        return "the local Tesseract OCR executable is missing"
    return "local OCR is available"


def extract_text(image_bytes: bytes, *, ocr_engine=None, image_module=None) -> str:
    """Extract text locally from PNG/JPEG/WebP bytes.

    `ocr_engine` and `image_module` are injectable for offline contract tests;
    production uses Pillow and pytesseract, backed by the local Tesseract binary.
    """
    if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
        raise ValueError("OCR needs non-empty image bytes")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("OCR image exceeds the 8 MB limit")
    if image_module is None:
        from PIL import Image as image_module
    if ocr_engine is None:
        import pytesseract
        ocr_engine = pytesseract.image_to_string

    with image_module.open(io.BytesIO(image_bytes)) as image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError("OCR image exceeds the 20 megapixel limit")
        image.verify()
    with image_module.open(io.BytesIO(image_bytes)) as image:
        text = ocr_engine(image.convert("RGB"), config="--psm 6", timeout=15)
    cleaned = "\n".join(line.rstrip() for line in str(text or "").splitlines()).strip()
    if len(cleaned) > MAX_TEXT_CHARS:
        cleaned = cleaned[:MAX_TEXT_CHARS] + "\n[OCR output truncated]"
    return cleaned
