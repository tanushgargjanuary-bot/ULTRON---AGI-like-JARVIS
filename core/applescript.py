"""core/applescript.py — put model-supplied text inside an AppleScript string, and keep it there.

`osascript -e` takes a whole program as one argument. Two actions built that program with an
f-string around text the model chose, on macOS:

    set frontmost of (first process whose name contains "{title}") to true
    set picture to POSIX file "{path}"

A title of `x") to true  --  do shell script "..."  --  ("` ends the string and the rest runs as
AppleScript, including `do shell script`. The Windows branch of the same action had already been
fixed (the PowerShell string doubles its quotes); the macOS branch had not. `quote` is the
equivalent for AppleScript: inside a double-quoted literal only a backslash and a double quote
mean anything, so those two are escaped and nothing else is.

It does not make text safe to put OUTSIDE a string literal, and it is not a substitute for
passing data as arguments where the tool allows it (`osascript -e '...' arg` and `on run argv`).
"""

from __future__ import annotations

__all__ = ["quote", "literal"]


def quote(text) -> str:
    """`text` as the inside of an AppleScript double-quoted string literal."""
    return str(text).replace("\x00", "").replace("\\", "\\\\").replace('"', '\\"')


def literal(text) -> str:
    """`text` as a complete AppleScript string literal, quotes included."""
    return '"' + quote(text) + '"'
