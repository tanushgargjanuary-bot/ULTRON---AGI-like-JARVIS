"""core/ocr.py — Local screen OCR without cloud models or data uploads.

Used by core/ui_ladder.py as a cheap, privacy-preserving rung before cloud vision.
Detects optional OCR libraries (pytesseract, easyocr) or local OCR bridges.
When missing, reports availability honestly so the ladder can fall through.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Optional

from core import failures


def ocr_available() -> tuple[bool, str]:
    """Check if any local OCR capability is available on this machine."""
    try:
        if importlib.util.find_spec("pytesseract") is not None:
            return True, "pytesseract"
    except Exception as exc:
        failures.note("ocr.probe_pytesseract", exc)

    try:
        if importlib.util.find_spec("easyocr") is not None:
            return True, "easyocr"
    except Exception as exc:
        failures.note("ocr.probe_easyocr", exc)

    return False, "no local OCR package installed"


def extract_words(image_source: str | Path | bytes) -> list[dict[str, Any]]:
    """Extract recognized words and bounding boxes from an image.

    Returns a list of dicts: [{"text": str, "x": int, "y": int, "w": int, "h": int}].
    Returns empty list if OCR is not available or recognition finds no text.
    """
    usable, engine = ocr_available()
    if not usable:
        return []

    try:
        if engine == "pytesseract":
            return _extract_pytesseract(image_source)
        if engine == "easyocr":
            return _extract_easyocr(image_source)
    except Exception as exc:
        failures.note("ocr.extract_words", exc)

    return []


def _extract_pytesseract(image_source: Any) -> list[dict[str, Any]]:
    import pytesseract  # type: ignore
    from PIL import Image

    img = Image.open(image_source) if isinstance(image_source, (str, Path)) else image_source
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    results: list[dict[str, Any]] = []
    for i in range(len(data.get("text", []))):
        w_text = str(data["text"][i]).strip()
        if w_text:
            results.append({
                "text": w_text,
                "x": int(data["left"][i]),
                "y": int(data["top"][i]),
                "w": int(data["width"][i]),
                "h": int(data["height"][i]),
            })
    return results


def _extract_easyocr(image_source: Any) -> list[dict[str, Any]]:
    import easyocr  # type: ignore

    reader = easyocr.Reader(["en"], verbose=False)
    raw = reader.readtext(image_source)
    results: list[dict[str, Any]] = []
    for bbox, text, _conf in raw:
        if text and text.strip():
            x_min = int(min(pt[0] for pt in bbox))
            y_min = int(min(pt[1] for pt in bbox))
            x_max = int(max(pt[0] for pt in bbox))
            y_max = int(max(pt[1] for pt in bbox))
            results.append({
                "text": text.strip(),
                "x": x_min,
                "y": y_min,
                "w": x_max - x_min,
                "h": y_max - y_min,
            })
    return results

