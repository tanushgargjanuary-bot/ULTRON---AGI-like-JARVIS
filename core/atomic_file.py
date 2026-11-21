"""core/atomic_file.py — the one retry for "another program has this file open".

Two stores replace a file by writing a temporary one beside it and renaming it over the
original (`memory/config_manager.py` for settings, `memory/memory_manager.py` for what the user
has asked to be remembered). On Windows the rename raises PermissionError while any other
program (an editor, a backup tool, antivirus) has the destination open, and the lock is usually
gone a moment later. Each store had its own copy of the same loop; this is the single one.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

__all__ = ["replace_with_retry"]


def replace_with_retry(source: Path, target: Path, attempts: int = 4) -> None:
    """`os.replace`, retried briefly when it raises PermissionError.

    Waits at most 0.3 s in total, which beats losing the write; any other error, and the
    last PermissionError, is raised at once so the caller can say the write did not happen.
    """
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))
