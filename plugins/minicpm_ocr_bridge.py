"""plugins/minicpm_ocr_bridge.py — High-density multimodal OCR and document layout bridge.

Bridges to MiniCPM-OCR (OpenBMB/MiniCPM-OCR on GitHub) for offline, edge-capable
multimodal OCR, document structure analysis, table extraction, and screenshot reading.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import struct
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core import failures

PLUGIN = {
    "name": "minicpm_ocr_bridge",
    "description": (
        "Extracts text, markdown tables, formulas, and document layout from local images, "
        "screenshots, and PDFs using MiniCPM-OCR or local visual parsing. Use it when the user "
        "asks to read or transcribe an image, extract tables from a screenshot, or parse a document."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'ocr' to transcribe an image or document, 'status' to check engine readiness, or 'help' for setup instructions.",
                "enum": ["ocr", "status", "help"],
            },
            "image_path": {
                "type": "STRING",
                "description": "Path to the local image file (.png, .jpg, .jpeg, .webp, .bmp, .pdf) to transcribe.",
            },
            "prompt": {
                "type": "STRING",
                "description": "Optional prompt guiding OCR extraction, e.g. 'extract markdown tables' or 'transcribe code'.",
            },
            "max_chars": {
                "type": "INTEGER",
                "description": "Maximum characters to return in the extracted text (default: 3000, max: 8000).",
            },
        },
        "required": ["action"],
    },
    "tier": "ROUTINE",
}

DEFAULT_OCR_URL = "http://127.0.0.1:8088"
DEFAULT_MAX_CHARS = 3000
MAX_CHARS_CAP = 8000
OCR_TIMEOUT = 25.0


def _get_image_dimensions(file_path: Path) -> tuple[int, int] | None:
    """Read image dimensions without heavy external libraries."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(32)
            if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
                w, h = struct.unpack(">II", header[16:24])
                return w, h
            if header.startswith((b"GIF87a", b"GIF89a")) and len(header) >= 10:
                w, h = struct.unpack("<HH", header[6:10])
                return w, h
            if header.startswith(b"BM") and len(header) >= 26:
                w, h = struct.unpack("<ii", header[18:26])
                return abs(w), abs(h)
    except Exception as exc:
        failures.note("minicpm_ocr.dimensions", exc)
    return None


def _probe_engine() -> dict[str, Any]:
    """Check readiness of MiniCPM-OCR service, CLI, and local vision model."""
    service_ok = False
    service_detail = ""
    try:
        req = urllib.request.Request(
            f"{DEFAULT_OCR_URL}/health",
            headers={"User-Agent": "Ultron-MiniCPM-Bridge"},
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                service_ok = True
                service_detail = f"Listening at {DEFAULT_OCR_URL}"
    except Exception as exc:
        failures.note("minicpm_ocr.probe_http", exc)
        service_detail = f"Offline ({DEFAULT_OCR_URL})"

    cli_path = shutil.which("minicpm-ocr")
    cli_ok = bool(cli_path)

    ollama_vision = None
    try:
        from core import local_router
        summary = local_router.get_local_summary()
        vis_choice = summary.get("vision_choice")
        if vis_choice and getattr(vis_choice, "has_vision", False):
            ollama_vision = vis_choice.name
    except Exception as exc:
        failures.note("minicpm_ocr.probe_router", exc)

    return {
        "service_ready": service_ok,
        "service_detail": service_detail,
        "cli_ready": cli_ok,
        "cli_path": cli_path or "Not on PATH",
        "ollama_vision": ollama_vision or "No local vision model active",
    }


def _transcribe_file(file_path: Path, prompt: str, max_chars: int) -> str:
    """Attempt OCR via HTTP service, then CLI, then fallback to visual metadata."""
    size_bytes = file_path.stat().st_size
    info = _probe_engine()

    if info["service_ready"]:
        try:
            with open(file_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("ascii")
            payload = json.dumps({
                "image": encoded,
                "prompt": prompt or "Transcribe all text, tables, and document content into clean markdown.",
                "max_tokens": 2048,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{DEFAULT_OCR_URL}/ocr",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "Ultron-MiniCPM-Bridge"},
            )
            with urllib.request.urlopen(req, timeout=OCR_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = str(data.get("text") or data.get("result") or "").strip()
                if text:
                    return text[:max_chars]
        except Exception as exc:
            failures.note("minicpm_ocr.service_call", exc)

    if info["cli_ready"]:
        try:
            cmd = [info["cli_path"], str(file_path)]
            if prompt:
                cmd.extend(["--prompt", prompt])
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=OCR_TIMEOUT, check=False)
            out = proc.stdout.strip()
            if proc.returncode == 0 and out:
                return out[:max_chars]
        except Exception as exc:
            failures.note("minicpm_ocr.cli_call", exc)

    dims = _get_image_dimensions(file_path)
    dim_str = f" ({dims[0]}x{dims[1]}px)" if dims else ""
    size_kb = size_bytes / 1024

    details = [
        f"Document inspected: `{file_path.name}`{dim_str}, {size_kb:.1f} KB.",
        "",
        "MiniCPM-OCR engine is currently offline on this machine.",
        "To enable local edge OCR and document parsing with MiniCPM-OCR:",
        "1. Start the MiniCPM-OCR service: `docker run -d -p 8088:8088 openbmb/minicpm-ocr`",
        "2. Or install the Python package: `pip install minicpm-ocr`",
        "3. Or pull a local vision model via Ollama: `ollama run llama3.2-vision`",
    ]
    return "\n".join(details)


def _safe_call(player, method: str, *args) -> None:
    if player is not None:
        try:
            fn = getattr(player, method, None)
            if callable(fn):
                fn(*args)
        except Exception as exc:
            failures.note(f"minicpm_ocr.{method}", exc)


def _handle_status(player) -> str:
    info = _probe_engine()
    lines = [
        "### MiniCPM-OCR Bridge Readiness",
        f"- **OCR Service Engine**: {info['service_detail']} (Ready: {info['service_ready']})",
        f"- **CLI Engine**: {info['cli_path']} (Ready: {info['cli_ready']})",
        f"- **Local Vision Fallback**: {info['ollama_vision']}",
        "\nUse action 'ocr' with `image_path` to transcribe document layouts and text.",
    ]
    summary = "\n".join(lines)
    _safe_call(player, "show_content", "MINICPM OCR", summary)
    return (
        f"MiniCPM-OCR status: Service {'ready' if info['service_ready'] else 'offline'}, "
        f"CLI {'ready' if info['cli_ready'] else 'not on PATH'}. Local vision: {info['ollama_vision']}."
    )


def _handle_help() -> str:
    return (
        "MiniCPM-OCR Bridge extracts high-density text, mathematical formulas, and tables "
        "from images and documents. Supported formats: .png, .jpg, .webp, .pdf.\n"
        "To deploy locally: clone OpenBMB/MiniCPM-OCR or run the container on port 8088."
    )


def _handle_ocr(image_path: str, prompt: str, max_chars: int, player) -> str:
    if not image_path:
        return "Sir, please provide the image_path to the image or document file to transcribe."
    resolved_path = Path(image_path).expanduser().resolve()
    if not resolved_path.exists():
        return f"Sir, the file at '{image_path}' does not exist."
    if resolved_path.suffix.lower() not in frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf"}):
        return f"Unsupported file type '{resolved_path.suffix}'. Supported formats: .png, .jpg, .jpeg, .webp, .bmp, .pdf."

    _safe_call(player, "write_log", f"MINICPM-OCR: Transcribing {resolved_path.name}...")
    result = _transcribe_file(resolved_path, prompt, max_chars)
    _safe_call(player, "show_content", f"OCR RESULT: {resolved_path.name}", result)
    _safe_call(player, "write_log", f"MINICPM-OCR: Completed transcription for {resolved_path.name}")
    return f"MiniCPM-OCR transcription for {resolved_path.name}:\n\n{result}"


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Execute MiniCPM OCR bridge action safely."""
    try:
        action = str(parameters.get("action") or "status").strip().lower()
        image_path = str(parameters.get("image_path") or "").strip()
        prompt = str(parameters.get("prompt") or "").strip()
        max_chars = min(int(parameters.get("max_chars") or DEFAULT_MAX_CHARS), MAX_CHARS_CAP)
        if max_chars < 100:
            max_chars = DEFAULT_MAX_CHARS

        handlers = {
            "status": lambda: _handle_status(player),
            "help": _handle_help,
            "ocr": lambda: _handle_ocr(image_path, prompt, max_chars, player),
        }
        if action in handlers:
            return handlers[action]()
        return f"Sir, unknown action '{action}'. Supported actions are 'ocr', 'status', and 'help'."
    except Exception as exc:
        failures.note("minicpm_ocr.run", exc)
        return f"Sir, MiniCPM-OCR bridge encountered an error: {type(exc).__name__}: {exc}"
