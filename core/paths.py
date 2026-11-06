"""core/paths.py — where Ultron keeps its own state, decided in one place.

Two modules used to answer this question differently (the service and, in this
build, the web cache). One answer, one function: `%LOCALAPPDATA%` on Windows,
`XDG_DATA_HOME` elsewhere, and a home-directory fallback so a stripped container
still works.
"""

from __future__ import annotations

import os
from pathlib import Path

FOLDER = "CustomMarkJarvis"


def state_dir() -> Path:
    """The folder for Ultron's own files: state, caches, the metacog ledger."""
    base = Path(
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("XDG_DATA_HOME")
        or Path.home() / ".local" / "share"
    )
    folder = base / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    return folder
