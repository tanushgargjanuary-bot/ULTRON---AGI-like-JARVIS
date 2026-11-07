"""core/context_detector.py — Active window and clipboard context detection.

Enables context-aware tool ranking and smart parameter auto-detection
without adding latency to the main voice loop.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core import failures

_DEV_PROCESSES = {
    "code.exe", "cursor.exe", "pycharm64.exe", "devenv.exe",
    "sublime_text.exe", "windowsterminal.exe", "powershell.exe",
    "cmd.exe", "git-bash.exe",
}
_BROWSER_PROCESSES = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe",
}
_MEDIA_PROCESSES = {
    "vlc.exe", "spotify.exe", "wmplayer.exe",
}


def detect_active_categories() -> list[str]:
    """Inspect the active foreground window to determine priority tool categories.

    Returns a list of matching category keys from tool_catalog.CATEGORY_ORDER,
    or an empty list if foreground context is unknown or unavailable.
    """
    try:
        from custom_jarvis.tools import get_active_window
        res = get_active_window()
        data = res.data if hasattr(res, "data") and isinstance(res.data, dict) else {}
        proc = str(data.get("process_name") or "").lower().strip()
        title = str(data.get("title") or "").lower().strip()

        if proc in _DEV_PROCESSES or any(dev in title for dev in ("visual studio code", "cursor", "pycharm")):
            return ["developer", "files"]
        if proc in _BROWSER_PROCESSES or any(b in title for b in ("google chrome", "microsoft edge", "mozilla firefox")):
            return ["knowledge"]
        if proc in _MEDIA_PROCESSES or "youtube" in title or "spotify" in title:
            return ["media"]
    except Exception as exc:  # noqa: BLE001
        failures.note("context_detector.detect_active_categories", exc)
    return []


def get_clipboard_target() -> str:
    """Safely inspect system clipboard for a target URL or valid local file path.

    Returns clean URL/path string if present, or an empty string.
    """
    try:
        import pyperclip
        raw = str(pyperclip.paste() or "").strip()
        if not raw:
            return ""
        if raw.startswith(("http://", "https://")) and len(raw) < 1000:
            return raw
        p = Path(raw)
        if p.exists() and len(raw) < 500:
            return str(p.resolve())
    except Exception as exc:  # noqa: BLE001
        failures.note("context_detector.get_clipboard_target", exc)
    return ""

