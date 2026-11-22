"""core/display_text.py — text that is shown to the owner for a decision, shown as it is.

A confirmation banner is the owner's only look at what he is approving. If what it draws is not what
it was given, the button approves something he did not see. Four things made it so, each found by
reading what the interface did with the text:

  * The label guessed whether the text was HTML. The first line of a prompt-change banner is the
    model's own `reason`, so `<b>shorter</b>` there made the whole text markup: new lines became
    spaces and `<!-- an instruction -->` in a changed line was not drawn at all.
  * The interface cut the detail at 300 characters, without a word. `core/custom_gate.py` lets the
    "Exact tool arguments" run to 64 KB, so most of what a person approved was never on screen.
  * A changed line that began `--` or `++` was taken for a diff header and dropped
    (`actions/prompt_editor.py`). `diff_rows` is that fix, written once: the system prompt's banner and
    the self-change banner (`actions/self_change.py`) both list the rows it returns.
  * Characters that change how text looks without showing up themselves — a right-to-left override
    that makes a program called `evil`, the override, `gpj.exe` display as `evilexe.jpg`, a
    zero-width space inside a word — passed straight through.

This is the part that needs no window, so it is tested without one: `tests/test_display_text.py`.
`ui.ConfirmBanner` draws what `for_banner` returns, as plain text, in a box that scrolls.
"""

from __future__ import annotations

import difflib
import unicodedata

__all__ = ["visible", "clip", "one_line", "for_banner", "diff_rows", "TITLE_LIMIT", "DETAIL_LIMIT"]

# The gate refuses arguments over 64 KB, so an approval is never clipped; the limit only keeps one
# runaway string from freezing the interface, and when it bites it says so.
DETAIL_LIMIT = 70_000
TITLE_LIMIT = 200

# Control, format (bidi marks, zero-width characters, the byte-order mark), surrogate, private-use,
# unassigned, and the two Unicode line/paragraph separators.
_INVISIBLE = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_KEPT = "\n\t"


def visible(text) -> str:
    """`text` with every character that can alter its appearance written out as an escape.

    A new line and a tab stay. Everything else in the categories above becomes `\\u202e` (or
    `\\U000e0001` beyond the first plane), so the owner reads what is there, not what it renders as.
    """
    out = []
    for char in str(text):
        if char not in _KEPT and unicodedata.category(char) in _INVISIBLE:
            code = ord(char)
            out.append(f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}")
        else:
            out.append(char)
    return "".join(out)


def clip(text, limit: int, what: str = "text") -> str:
    """`text`, or its first `limit` characters followed by a line that says how many are missing.

    Never silent: a result longer than `limit` always ends with the marker.
    """
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… ({len(text) - limit:,} more characters of {what} are not shown here)"


def one_line(text, limit: int) -> str:
    """`text` on one line, escaped, and cut with a visible `…` when it is longer than `limit`."""
    flat = " ".join(visible(text).split())
    return flat if len(flat) <= limit else flat[:limit].rstrip() + "…"


def diff_rows(before: str, after: str) -> list[str]:
    """Every changed line, in order, as `-removed` and `+added`, from a real diff.

    `unified_diff` opens with two header rows (`--- ` and `+++ `) and writes an `@@` row for each hunk.
    They are dropped by their position and by that shape, never by how a row begins: a changed line
    whose text starts `--` or `++` makes a content row that starts `---` or `+++`, and a filter on
    those prefixes drops exactly the lines it should show.

    A line that appears elsewhere in the file is still a changed line when it is added or removed
    here: this compares positions, not sets of lines.
    """
    rows = list(difflib.unified_diff(str(before).splitlines(), str(after).splitlines(),
                                     lineterm="", n=0))
    return [row for row in rows[2:] if not row.startswith("@@")]


def for_banner(title, detail) -> tuple[str, str]:
    """The (title, detail) a banner should draw: escaped, and clipped only with a marker."""
    return (clip(visible(title), TITLE_LIMIT, "the title"),
            clip(visible(detail), DETAIL_LIMIT, "the details"))
