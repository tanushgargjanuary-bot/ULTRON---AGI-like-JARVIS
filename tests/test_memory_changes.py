"""A fact that changed must leave a trace of what it was.

The store is a dictionary of facts. It always had a date; what it never had was the
value that was there before, so "you told me the opposite last week" could only be
answered with a guess. The history lives in its own bounded file so the facts keep
their room.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from memory import memory_manager as mm


class _Store(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        folder = Path(self._temp.name)
        self._saved = (mm.MEMORY_PATH, mm.CHANGES_PATH)
        mm.MEMORY_PATH = folder / "long_term.json"
        mm.CHANGES_PATH = folder / "changes.json"
        mm.MEMORY_PATH.write_text(json.dumps({}), encoding="utf-8")

    def tearDown(self):
        mm.MEMORY_PATH, mm.CHANGES_PATH = self._saved
        self._temp.cleanup()

    def write(self, update):
        return mm.update_memory(update)


class WhatChanged(_Store):
    def test_a_new_fact_records_what_it_replaced(self):
        self.write({"preferences": {"answer_length": "long"}})
        self.write({"preferences": {"answer_length": "short"}})
        rows = mm.changes()
        self.assertTrue(rows)
        newest = rows[0]
        self.assertEqual(newest["path"], "preferences/answer_length")
        self.assertEqual(newest["from"], "long")
        self.assertEqual(newest["to"], "short")
        self.assertIn("at", newest)

    def test_the_same_value_written_twice_is_not_a_change(self):
        self.write({"preferences": {"answer_length": "short"}})
        self.write({"preferences": {"answer_length": "short"}})
        self.assertEqual(len(mm.changes()), 1)

    def test_a_nested_fact_is_named_by_its_path(self):
        self.write({"projects": {"thesis": "chapter two"}})
        self.write({"projects": {"thesis": "chapter three"}})
        self.assertEqual(mm.changes()[0]["path"], "projects/thesis")

    def test_the_history_is_bounded(self):
        for number in range(mm.CHANGES_MAX + 25):
            self.write({"notes": {"counter": f"value {number}"}})
        self.assertEqual(len(mm.changes(limit=mm.CHANGES_MAX)), mm.CHANGES_MAX)
        rows = json.loads(mm.CHANGES_PATH.read_text(encoding="utf-8"))
        self.assertLessEqual(len(rows), mm.CHANGES_MAX)

    def test_the_newest_change_is_first(self):
        for value in ("one", "two", "three"):
            self.write({"notes": {"word": value}})
        self.assertEqual(mm.changes()[0]["to"], "three")

    def test_recall_shows_when_a_fact_was_updated(self):
        self.write({"preferences": {"answer_length": "short"}})
        result = mm.search_memory("answer length")
        self.assertIn("last updated", result)
        self.assertIn("T", result)

    def test_the_store_does_not_grow_a_history_of_its_own(self):
        self.write({"preferences": {"tone": "plain"}})
        self.write({"preferences": {"tone": "warm"}})
        stored = json.loads(mm.MEMORY_PATH.read_text(encoding="utf-8"))
        entry = stored["preferences"]["tone"]
        self.assertEqual(set(entry), {"value", "updated", "updated_at"})
        self.assertIn("T", entry["updated_at"])

    def test_a_missing_history_file_is_not_an_error(self):
        mm.CHANGES_PATH.unlink(missing_ok=True)
        self.assertEqual(mm.changes(), [])

    def test_a_damaged_history_file_is_read_as_empty(self):
        mm.CHANGES_PATH.write_text("{not a list", encoding="utf-8")
        self.assertEqual(mm.changes(), [])

    def test_a_failed_write_of_the_history_does_not_lose_the_fact(self):
        write_text = Path.write_text

        def fail_history(path, *args, **kwargs):
            if path == mm.CHANGES_PATH:
                raise OSError("disk full")
            return write_text(path, *args, **kwargs)

        with mock.patch.object(Path, "write_text", new=fail_history):
            self.write({"preferences": {"answer_length": "short"}})
        stored = json.loads(mm.MEMORY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(stored["preferences"]["answer_length"]["value"], "short")


if __name__ == "__main__":
    unittest.main()
