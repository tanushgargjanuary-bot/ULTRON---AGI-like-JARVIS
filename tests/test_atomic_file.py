"""`core.atomic_file.replace_with_retry`: the loop both stores share."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import atomic_file


class ReplaceWithRetry(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.folder = Path(self._temp.name)
        self.source = self.folder / "new"
        self.target = self.folder / "old"
        self.source.write_text("new", encoding="utf-8")
        self.target.write_text("old", encoding="utf-8")

    def test_it_replaces(self):
        atomic_file.replace_with_retry(self.source, self.target)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "new")
        self.assertFalse(self.source.exists())

    def test_a_permission_error_is_retried_and_then_succeeds(self):
        real = os.replace
        tries = []

        def flaky(source, target):
            tries.append(1)
            if len(tries) < 3:
                raise PermissionError("in use")
            return real(source, target)

        slept = []
        with mock.patch.object(atomic_file.os, "replace", flaky), \
                mock.patch.object(atomic_file.time, "sleep", slept.append):
            atomic_file.replace_with_retry(self.source, self.target)
        self.assertEqual(len(tries), 3)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "new")
        self.assertEqual(slept, [0.05, 0.1])

    def test_the_last_permission_error_is_raised(self):
        with mock.patch.object(atomic_file.os, "replace", side_effect=PermissionError("in use")), \
                mock.patch.object(atomic_file.time, "sleep"):
            with self.assertRaises(PermissionError):
                atomic_file.replace_with_retry(self.source, self.target, attempts=3)

    def test_the_total_wait_stays_short(self):
        slept = []
        with mock.patch.object(atomic_file.os, "replace", side_effect=PermissionError("in use")), \
                mock.patch.object(atomic_file.time, "sleep", slept.append):
            with self.assertRaises(PermissionError):
                atomic_file.replace_with_retry(self.source, self.target)
        self.assertLessEqual(sum(slept), 0.35)

    def test_any_other_error_is_raised_at_once(self):
        with mock.patch.object(atomic_file.os, "replace", side_effect=FileNotFoundError("gone")) as m, \
                mock.patch.object(atomic_file.time, "sleep") as sleeper:
            with self.assertRaises(FileNotFoundError):
                atomic_file.replace_with_retry(self.source, self.target)
        self.assertEqual(m.call_count, 1)
        sleeper.assert_not_called()

    def test_the_config_store_uses_this_loop_and_not_a_copy(self):
        from memory import config_manager, memory_manager
        self.assertIs(config_manager._replace_with_retry, atomic_file.replace_with_retry)
        self.assertIs(memory_manager.replace_with_retry, atomic_file.replace_with_retry)


if __name__ == "__main__":
    unittest.main()
