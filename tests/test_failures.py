"""The note-taker: it records, it never raises, and it stays small.

The point of `core/failures.py` is that a failure nobody can fix still leaves a
trace. These tests check the three properties that make that true — it records, it
cannot raise, and it cannot grow without limit — plus the one thing that would make
it useless in practice: swallowing the note about itself.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import failures


class TheNoteTaker(unittest.TestCase):
    def setUp(self):
        failures.clear()

    def tearDown(self):
        failures.clear()

    def test_it_records_what_was_caught_and_where(self):
        try:
            raise PermissionError("the window will not take focus")
        except Exception as error:
            failures.note("appidentity.focus", error)
        trail = failures.recent()
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0]["where"], "appidentity.focus")
        self.assertEqual(trail[0]["kind"], "PermissionError")
        self.assertIn("focus", trail[0]["error"])

    def test_a_note_carries_the_line_it_came_from(self):
        # A trail without a line number is a rumour.
        try:
            raise ValueError("bad")
        except Exception as error:
            failures.note("somewhere", error)
        self.assertTrue(failures.recent()[-1]["at"])

    def test_it_accepts_a_sentence_instead_of_an_exception(self):
        failures.note("boot", "the sidecar was missing")
        entry = failures.recent()[-1]
        self.assertEqual(entry["kind"], "Message")
        self.assertEqual(entry["error"], "the sidecar was missing")

    def test_it_never_raises_even_when_the_error_is_hostile(self):
        class Hostile(Exception):
            def __str__(self):
                raise RuntimeError("no")

        failures.note("hostile", Hostile())        # must not raise
        self.assertEqual(failures.recent(), [])

    def test_the_trail_is_bounded(self):
        for index in range(failures.KEEP + 50):
            failures.note("loop", f"number {index}")
        self.assertEqual(len(failures.recent(limit=failures.KEEP + 100)),
                         failures.KEEP)
        self.assertEqual(failures.recent()[-1]["error"], f"number {failures.KEEP + 49}")

    def test_the_summary_counts_by_part(self):
        failures.note("audio.open", "no device")
        failures.note("audio.open", "no device")
        failures.note("sidecar.start", "missing")
        self.assertEqual(failures.summary(), {"audio.open": 2, "sidecar.start": 1})

    def test_clear_empties_it(self):
        failures.note("x", "y")
        failures.clear()
        self.assertEqual(failures.recent(), [])


class EveryCallSiteCanSeeIt(unittest.TestCase):
    """The mistake this build made: the call was written, the import was not.

    A mechanical edit added `failures.note(...)` to forty-three handlers and forgot
    `from core import failures` in one file. Every test still passed, because the
    line only runs when something has already failed — so the note-taker was found
    by a test that deliberately broke an adapter, and it crashed with NameError
    instead of recording. This is the cheapest possible guard against that class.
    """

    def test_a_module_that_notes_a_failure_imports_the_note_taker(self):
        import ast

        offenders = []
        for path in sorted(ROOT.rglob("*.py")):
            if ".git" in path.parts or path.name == "failures.py":
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            if "failures.note(" not in source:
                continue
            tree = ast.parse(source)
            imported = False
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module in {
                        "core", "core.failures", "failures"}:
                    if any(alias.name == "failures" for alias in node.names):
                        imported = True
                if isinstance(node, ast.Import) and any(
                        alias.name in {"core.failures", "failures"} for alias in node.names):
                    imported = True
            if not imported:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], "these call the note-taker without importing it")


class NothingInTheOwnedCoreSwallows(unittest.TestCase):
    """The promise this build makes, checked against the source itself."""

    def test_core_and_providers_never_catch_an_exception_and_drop_it(self):
        import ast

        # One definition of "catches everything", shared with the scan, so the two
        # cannot disagree about a tuple or a dotted name. The first version of this
        # test wrote its own and called four honest `except (OSError, ValueError)`
        # handlers offenders.
        from scripts.deep_scan import catches_everything

        offenders = []
        for folder in ("core", "providers"):
            for path in (ROOT / folder).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ExceptHandler):
                        continue
                    if len(node.body) != 1:
                        continue
                    if not isinstance(node.body[0], (ast.Pass, ast.Continue)):
                        continue
                    if catches_everything(node.type):
                        offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [],
                         "a failure in the owned core must leave a note, not vanish")


if __name__ == "__main__":
    unittest.main()
