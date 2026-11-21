"""What the user asked to be remembered must survive a crash, a bad file and a busy file.

`memory/memory_manager.py` keeps `long_term.json`, the one file holding what the user has
approved for permanent memory. Its failure behaviour was:

* every write was `Path.write_text`, which truncates the file and then writes it: a crash, a
  full disk or a kill in between left half a file;
* a file that could not be parsed (that half file, or a store a text editor had saved with a
  byte-order mark, which plain utf-8 hands to `json.loads` as an illegal character) made
  `load_memory()` answer "empty", and the NEXT save replaced the file with that emptiness:
  one new fact, everything else gone, nothing said;
* the same happened for a file that merely could not be READ at that moment;
* a write that failed was still reported: `remember()` said "Remembered", and
  `core/memory_consent.request_write` said "Remembered ... in ...";
* `actions/background_monitor.py` did its own read-modify-write beside the manager's lock.
"""

from __future__ import annotations

import builtins
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from core import atomic_file, failures
from memory import memory_manager as mm

FACTS = {"identity": {"name": {"value": "Asha"}}, "notes": {"dentist": {"value": "Tuesday"}}}


class WithAStore(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        folder = Path(self._temp.name)
        patcher = mock.patch.multiple(
            mm, MEMORY_PATH=folder / "long_term.json", CHANGES_PATH=folder / "changes.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        notifier = []
        mm.set_trim_notifier(notifier.append)
        self.addCleanup(mm.set_trim_notifier, None)
        self.said = notifier
        failures.clear()
        self.addCleanup(failures.clear)
        self.folder = folder

    def seed(self, text_or_bytes):
        data = text_or_bytes if isinstance(text_or_bytes, bytes) else text_or_bytes.encode("utf-8")
        mm.MEMORY_PATH.write_bytes(data)

    def stored(self):
        return json.loads(mm.MEMORY_PATH.read_text(encoding="utf-8"))

    def broken_files(self):
        return sorted(self.folder.glob("long_term.json.broken-*"))


class ABomIsNotDamage(WithAStore):
    def test_a_store_saved_with_a_byte_order_mark_loads_and_keeps_its_facts(self):
        self.seed(b"\xef\xbb\xbf" + json.dumps(FACTS).encode("utf-8"))
        loaded = mm.load_memory()
        self.assertEqual(loaded["identity"]["name"]["value"], "Asha")
        mm.update_memory({"notes": {"k": {"value": "v"}}})
        after = self.stored()
        self.assertEqual(after["identity"]["name"]["value"], "Asha", "nothing was lost")
        self.assertEqual(after["notes"]["k"]["value"], "v")
        self.assertEqual(self.broken_files(), [], "a BOM is not damage")

    def test_pop_last_session_reads_a_bom_store_too(self):
        data = dict(FACTS, sessions=[{"date": "2026-11-01", "summary": "talked about the dentist"}])
        self.seed(b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8"))
        entry = mm.pop_last_session()
        self.assertEqual(entry["summary"], "talked about the dentist")
        self.assertEqual(self.stored()["identity"]["name"]["value"], "Asha")


class ADamagedFileIsKeptNotReplaced(WithAStore):
    def test_half_a_file_is_set_aside_with_its_bytes_and_the_user_is_told(self):
        half = json.dumps(FACTS)[:40]
        self.seed(half)
        self.assertEqual(mm.load_memory()["notes"], {})
        broken = self.broken_files()
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0].read_text(encoding="utf-8"), half, "the bytes are kept")
        self.assertFalse(mm.MEMORY_PATH.exists(), "nothing left to be overwritten")
        self.assertEqual(len(self.said), 1)
        self.assertIn(broken[0].name, self.said[0])
        self.assertTrue(any(n["where"] == "memory.load" for n in failures.recent()))

    def test_the_next_save_does_not_destroy_the_damaged_original(self):
        half = json.dumps(FACTS)[:40]
        self.seed(half)
        mm.update_memory({"notes": {"k": {"value": "v"}}})
        self.assertEqual(self.stored()["notes"]["k"]["value"], "v")
        self.assertEqual(self.broken_files()[0].read_text(encoding="utf-8"), half)

    def test_a_list_shaped_file_is_kept_too(self):
        self.seed("[1, 2, 3]")
        mm.update_memory({"notes": {"k": {"value": "v"}}})
        self.assertEqual(self.broken_files()[0].read_text(encoding="utf-8"), "[1, 2, 3]")

    def test_a_file_that_is_not_text_is_kept(self):
        self.seed(b"\xff\xfe\x00\x81 not utf-8 \xc3\x28")
        self.assertEqual(mm.load_memory()["notes"], {})
        self.assertEqual(len(self.broken_files()), 1)

    def test_two_damaged_files_in_one_second_do_not_overwrite_each_other(self):
        with mock.patch.object(mm.time, "time", return_value=1_700_000_000.0):
            self.seed("{first")
            mm.load_memory()
            self.seed("{second")
            mm.load_memory()
        texts = sorted(p.read_text(encoding="utf-8") for p in self.broken_files())
        self.assertEqual(texts, ["{first", "{second"])

    def test_an_empty_file_is_not_worth_keeping(self):
        self.seed("")
        self.assertEqual(mm.load_memory()["notes"], {})
        self.assertEqual(self.broken_files(), [])
        self.assertEqual(self.said, [])

    def test_when_the_damaged_file_cannot_be_moved_the_save_is_refused(self):
        half = json.dumps(FACTS)[:40]
        self.seed(half)
        with mock.patch.object(mm.os, "replace", side_effect=PermissionError("locked")):
            loaded = mm.load_memory()
            self.assertEqual(loaded["notes"], {})
            with self.assertRaises(mm.MemoryWriteError):
                mm.save_memory(loaded)
        self.assertEqual(mm.MEMORY_PATH.read_text(encoding="utf-8"), half)


class AFileThatCannotBeReadRightNowIsNotAnEmptyMemory(WithAStore):
    def test_a_read_error_never_becomes_a_save_that_replaces_everything(self):
        self.seed(json.dumps(FACTS))
        real = Path.read_text

        def locked(path, *args, **kwargs):
            if path == mm.MEMORY_PATH:
                raise PermissionError("another program has it open")
            return real(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", locked):
            with self.assertRaises(mm.MemoryWriteError):
                mm.update_memory({"notes": {"k": {"value": "v"}}})
        self.assertEqual(self.stored(), FACTS, "the file is exactly what it was")
        self.assertEqual(self.broken_files(), [], "a healthy file is not set aside")

    def test_once_it_can_be_read_again_saving_works(self):
        self.seed(json.dumps(FACTS))
        mm.update_memory({"notes": {"k": {"value": "v"}}})
        after = self.stored()
        self.assertEqual(after["identity"]["name"]["value"], "Asha")
        self.assertEqual(after["notes"]["k"]["value"], "v")


class AWriteIsAllOrNothing(WithAStore):
    def test_a_failure_during_the_write_leaves_the_old_file_and_no_litter(self):
        self.seed(json.dumps(FACTS))
        before = mm.MEMORY_PATH.read_bytes()
        with mock.patch.object(mm.os, "fsync", side_effect=OSError("No space left on device")):
            with self.assertRaises(mm.MemoryWriteError):
                mm.update_memory({"notes": {"k": {"value": "v"}}})
        self.assertEqual(mm.MEMORY_PATH.read_bytes(), before)
        self.assertEqual(list(self.folder.glob(".long_term.json.*.tmp")), [])

    def test_a_replace_that_always_fails_is_reported_and_cleans_up(self):
        self.seed(json.dumps(FACTS))
        before = mm.MEMORY_PATH.read_bytes()
        with mock.patch.object(mm.os, "replace", side_effect=PermissionError("locked")), \
                mock.patch.object(atomic_file.time, "sleep"):
            with self.assertRaises(mm.MemoryWriteError):
                mm.update_memory({"notes": {"k": {"value": "v"}}})
        self.assertEqual(mm.MEMORY_PATH.read_bytes(), before)
        self.assertEqual(list(self.folder.glob(".long_term.json.*.tmp")), [])

    def test_a_replace_that_is_briefly_locked_succeeds(self):
        self.seed(json.dumps(FACTS))
        real = os.replace
        calls = []

        def flaky(source, target, *args, **kwargs):
            if Path(target) != mm.MEMORY_PATH:        # the history file is not under test
                return real(source, target, *args, **kwargs)
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("held by an antivirus scan")
            return real(source, target, *args, **kwargs)

        with mock.patch.object(mm.os, "replace", side_effect=flaky), \
                mock.patch.object(atomic_file.time, "sleep"):
            mm.update_memory({"notes": {"k": {"value": "v"}}})
        self.assertEqual(self.stored()["notes"]["k"]["value"], "v")
        self.assertEqual(len(calls), 3)

    def test_no_write_goes_through_write_text_any_more(self):
        self.seed(json.dumps(FACTS))
        with mock.patch.object(Path, "write_text", side_effect=AssertionError("write_text")):
            mm.update_memory({"notes": {"a": {"value": "1"}}})
            mm.save_session_summary("a short talk", "en")
            self.assertIsNotNone(mm.pop_last_session())
            mm.set_top_level("monitors", {"x": {"topic": "t"}})
        self.assertEqual(self.stored()["monitors"], {"x": {"topic": "t"}})

    def test_the_store_is_not_world_readable(self):
        if os.name != "posix":
            self.skipTest("file modes are a POSIX idea")
        mm.update_memory({"notes": {"a": {"value": "1"}}})
        self.assertEqual(mm.MEMORY_PATH.stat().st_mode & 0o077, 0,
                         "what a person told their assistant is private")


class WhatIsSaidIsWhatHappened(WithAStore):
    def refusing(self):
        return mock.patch.object(mm.os, "replace", side_effect=OSError("disk full"))

    def test_remember_does_not_claim_a_save_that_failed(self):
        with self.refusing():
            answer = mm.remember("name", "Asha", "identity")
        self.assertNotIn("Remembered", answer)
        self.assertIn("Nothing was saved", answer)

    def test_remember_still_says_so_when_it_worked(self):
        self.assertEqual(mm.remember("name", "Asha", "identity"),
                         "Remembered: identity/name = Asha")

    def test_forget_does_not_claim_a_removal_that_failed(self):
        mm.remember("dentist", "Tuesday")
        with self.refusing():
            answer = mm.forget("dentist")
        self.assertNotIn("Forgotten", answer)
        self.assertEqual(self.stored()["notes"]["dentist"]["value"], "Tuesday")

    def test_the_approved_memory_write_reports_the_failure_instead_of_remembered(self):
        # core/memory_consent.request_write: the gate's `run` raises, and core/confirm
        # logs "ERR: ... failed" instead of "Confirmed - Remembered".
        from core import memory_consent

        outcome = {}

        def gate(key, title, detail, run):
            try:
                outcome["said"] = run()
            except Exception as error:               # what confirm._worker does
                outcome["error"] = error
            return "ok"

        class Allowed:
            allow = False

        with self.refusing():
            memory_consent.request_write("notes", "k", "v", mm.update_memory,
                                         gate=gate, decide=lambda *a, **k: Allowed())
        self.assertNotIn("said", outcome)
        self.assertIsInstance(outcome["error"], mm.MemoryWriteError)

    def test_a_session_summary_that_could_not_be_saved_is_not_announced(self):
        printed = []
        with self.refusing(), mock.patch.object(builtins, "print", side_effect=printed.append):
            mm.save_session_summary("we talked", "en")
        self.assertFalse(any("Session saved" in str(line) for line in printed), printed)


class OneWriterForTheMonitorList(WithAStore):
    def test_saving_monitors_keeps_every_other_key(self):
        from actions import background_monitor
        mm.update_memory({"identity": {"name": {"value": "Asha"}}})
        background_monitor._save({"rain": {"topic": "rain"}})
        after = self.stored()
        self.assertEqual(after["identity"]["name"]["value"], "Asha")
        self.assertEqual(after["monitors"], {"rain": {"topic": "rain"}})

    def test_monitor_saves_and_fact_saves_do_not_lose_each_other(self):
        from actions import background_monitor
        errors = []

        def facts():
            try:
                for index in range(40):
                    mm.update_memory({"notes": {f"f{index}": {"value": str(index)}}})
            except Exception as error:               # pragma: no cover - reported below
                errors.append(error)

        def monitors():
            try:
                for index in range(40):
                    background_monitor._save({f"m{index}": {"topic": str(index)}})
            except Exception as error:               # pragma: no cover - reported below
                errors.append(error)

        threads = [threading.Thread(target=facts), threading.Thread(target=monitors)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        after = self.stored()
        self.assertEqual(len(after["notes"]), 40, "no fact was overwritten by a monitor save")
        self.assertEqual(list(after["monitors"]), ["m39"])

    def test_add_monitor_does_not_claim_what_it_could_not_save(self):
        from actions import background_monitor
        with mock.patch.object(mm.os, "replace", side_effect=OSError("disk full")):
            said = background_monitor.add_monitor("Rain forecasts")
        self.assertNotIn("Now monitoring", said)
        self.assertIn("could not save", said)


if __name__ == "__main__":
    unittest.main()
