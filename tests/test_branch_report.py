"""Tests for the branch report: parsing, grouping, and the shallow-clone note.

The report is read-only, so everything here is a pure function over text. No network, no
real branch switching, no dependence on which branches exist on this machine.
"""

from __future__ import annotations

import unittest

from scripts.branch_report import _groups, _parse_refs


RAW = (
    "main\t44ec6dbde86\t2026-11-07\trevert: keep review changes on chatgpt\n"
    "ArenaAi\t44ec6dbde86\t2026-11-07\trevert: keep review changes on chatgpt\n"
    "chatgpt\t49ff63f84c8\t2026-11-07\tdocs: record routing checks and execution limit\n"
)


class Parsing(unittest.TestCase):
    def test_a_row_keeps_name_commit_date_and_subject(self):
        rows = _parse_refs(RAW)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["name"], "main")
        self.assertEqual(rows[0]["sha"], "44ec6dbde86")
        self.assertEqual(rows[0]["date"], "2026-11-07")
        self.assertEqual(rows[0]["subject"], "revert: keep review changes on chatgpt")

    def test_a_tab_inside_a_subject_does_not_lose_the_subject(self):
        rows = _parse_refs("main\tabc123456789\t2026-11-07\tone\ttwo\n")
        self.assertEqual(rows[0]["subject"], "one\ttwo")

    def test_a_short_line_is_dropped_rather_than_invented(self):
        self.assertEqual(_parse_refs("main\tabc123456789\n"), [])
        self.assertEqual(_parse_refs(""), [])
        self.assertEqual(_parse_refs("\n\n"), [])


class Grouping(unittest.TestCase):
    def test_two_names_on_one_commit_are_reported_together(self):
        groups = _groups(_parse_refs(RAW))
        self.assertEqual(groups["44ec6dbde86"], ["main", "ArenaAi"])
        self.assertEqual(groups["49ff63f84c8"], ["chatgpt"])

    def test_every_name_appears_exactly_once(self):
        rows = _parse_refs(RAW)
        names = [name for names in _groups(rows).values() for name in names]
        self.assertEqual(sorted(names), sorted(row["name"] for row in rows))


if __name__ == "__main__":
    unittest.main()
