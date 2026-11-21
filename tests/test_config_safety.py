"""`memory/config_manager.py` must never lose the owner's keys.

This file holds the regression tests for four ways `api_keys.json` lost data. All
four were reproduced before they were fixed; the numbers are in the comments.

1. A READ that fails for a moment (another process has the file open) was treated
   as an empty file, and the next setter wrote that emptiness back over every key.
2. Two writers shared ONE temporary file, `api_keys.json.tmp`. A burst of eight
   threads making 320 tool calls — `core/tool_usage.py` saves a setting on every
   call — left a config with neither the Gemini key nor the providers in 3 runs of
   3, with torn JSON visible to readers and 97-120 "could not save" messages.
3. Read-modify-write was not atomic, so concurrent setters overwrote each other
   (4-26 of 320 usage counts survived).
4. The first-run screen was told "saved" when nothing had been written.
"""

from __future__ import annotations

import builtins
import json
import os
import threading
import unittest
from pathlib import Path
from unittest import mock

try:
    from tempconfig import WithATemporaryConfig, cm
except ImportError:                       # imported as tests.test_config_safety
    from tests.tempconfig import WithATemporaryConfig, cm

from core import failures, tool_usage

SECRETS = {
    "gemini_api_key": "AIza-REAL-KEY-0123456789",
    "providers": {"creds": {"openai_compat@groq": {"api_key": "sk-keep-me"}}},
}


def _quiet():
    """The setters print a line for every failure; the tests cause failures on purpose."""
    return mock.patch.object(builtins, "print")


def _locked_read(real):
    """A `Path.read_bytes` that fails for the settings file only, like a sharing violation."""
    def fake(self, *args, **kwargs):
        if self == cm.CONFIG_FILE:
            raise PermissionError(13, "The process cannot access the file because it is "
                                      "being used by another process")
        return real(self, *args, **kwargs)
    return fake


class ANeverEmptyRead(WithATemporaryConfig):
    def setUp(self):
        super().setUp()
        failures.clear()
        self.write_settings(dict(SECRETS))

    def test_a_failed_read_does_not_become_an_empty_config(self):
        before = cm.CONFIG_FILE.read_bytes()
        with mock.patch.object(Path, "read_bytes", _locked_read(Path.read_bytes)), _quiet():
            cm.save_digest_hour("07:30")                 # an innocent, unrelated setting
            cm.save_ui_scale(1.2)
        self.assertEqual(cm.CONFIG_FILE.read_bytes(), before,
                         "the file must be exactly as it was")
        self.assertEqual(self.read_settings()["gemini_api_key"], SECRETS["gemini_api_key"])
        self.assertEqual(list(cm.CONFIG_DIR.glob("*.broken-*")), [])
        wheres = {n["where"] for n in failures.recent()}
        self.assertLessEqual({"config_manager.read", "config_manager.write"}, wheres,
                             "the refusal must leave a trail")

    def test_the_setting_saves_once_the_file_can_be_read_again(self):
        with mock.patch.object(Path, "read_bytes", _locked_read(Path.read_bytes)), _quiet():
            cm.save_digest_hour("07:30")
        cm.save_digest_hour("07:30")
        saved = self.read_settings()
        self.assertEqual(saved["digest_hour"], "07:30")
        self.assertIn("providers", saved)

    def test_a_damaged_file_that_cannot_be_copied_aside_is_not_overwritten(self):
        cm.CONFIG_FILE.write_text('{"gemini_api_key": "AIzaHALF', encoding="utf-8")
        before = cm.CONFIG_FILE.read_bytes()
        real = Path.write_bytes

        def no_backup(self, data):
            if ".broken-" in self.name:
                raise OSError(28, "No space left on device")
            return real(self, data)

        with mock.patch.object(Path, "write_bytes", no_backup), _quiet():
            cm.save_ui_scale(1.3)
        self.assertEqual(cm.CONFIG_FILE.read_bytes(), before,
                         "the only copy of the damaged keys must survive")
        self.assertIn("config_manager.backup", {n["where"] for n in failures.recent()})

    def test_a_damaged_file_is_still_backed_up_and_the_setting_still_saves(self):
        cm.CONFIG_FILE.write_bytes(b'{"gemini_api_key": "AIzaHALF')
        with _quiet():
            cm.save_ui_scale(1.3)
        kept = list(cm.CONFIG_DIR.glob("api_keys.json.broken-*"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_bytes(), b'{"gemini_api_key": "AIzaHALF')
        self.assertEqual(cm.get_ui_scale(), 1.3)

    def test_a_utf8_byte_order_mark_is_not_damage(self):
        # Notepad and Windows PowerShell add one. It used to make json fail, so a
        # hand-edited file read as "no keys at all" and the next save replaced it.
        cm.CONFIG_FILE.write_bytes(b"\xef\xbb\xbf" + json.dumps(SECRETS).encode("utf-8"))
        self.assertEqual(cm.load_api_keys()["gemini_api_key"], SECRETS["gemini_api_key"])
        cm.save_ui_scale(1.3)
        self.assertEqual(list(cm.CONFIG_DIR.glob("*.broken-*")), [])
        saved = self.read_settings()
        self.assertEqual(saved["gemini_api_key"], SECRETS["gemini_api_key"])
        self.assertEqual(saved["ui_scale"], 1.3)

    def test_binary_garbage_is_kept_as_bytes_not_lost(self):
        garbage = b"\xff\xfe\x00\x81 not text at all"
        cm.CONFIG_FILE.write_bytes(garbage)
        with _quiet():
            cm.save_ui_scale(1.3)
        kept = list(cm.CONFIG_DIR.glob("api_keys.json.broken-*"))
        self.assertEqual([k.read_bytes() for k in kept], [garbage])
        self.assertEqual(cm.get_ui_scale(), 1.3)


class AtomicAndPrivateWrites(WithATemporaryConfig):
    def setUp(self):
        super().setUp()
        failures.clear()
        self.write_settings(dict(SECRETS))

    @unittest.skipIf(os.name == "nt", "POSIX permission bits do not apply on Windows")
    def test_the_secrets_file_is_owner_only(self):
        cm.save_ui_scale(1.3)
        self.assertEqual(cm.CONFIG_FILE.stat().st_mode & 0o777, 0o600)

    def test_the_temporary_file_name_is_not_shared(self):
        seen = []
        real = os.replace

        def spy(src, dst):
            seen.append(Path(src).name)
            return real(src, dst)

        with mock.patch.object(cm.os, "replace", spy):
            cm.save_ui_scale(1.3)
            cm.save_ui_scale(1.4)
        self.assertEqual(len(seen), 2)
        self.assertNotEqual(seen[0], seen[1])
        self.assertTrue(all(n.startswith("api_keys.json.") and n.endswith(".tmp")
                            for n in seen), seen)

    def test_a_replace_that_fails_briefly_is_retried(self):
        real = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError(32, "being used by another process")
            return real(src, dst)

        with mock.patch.object(cm.os, "replace", flaky), \
                mock.patch.object(cm.time, "sleep"):
            self.assertTrue(cm._write_config({"ok": True}))
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.read_settings(), {"ok": True})

    def test_a_replace_that_keeps_failing_returns_false_and_cleans_up(self):
        before = cm.CONFIG_FILE.read_bytes()

        def always(_src, _dst):
            raise PermissionError(5, "Access is denied")

        with mock.patch.object(cm.os, "replace", always), \
                mock.patch.object(cm.time, "sleep"), _quiet():
            self.assertFalse(cm._write_config({"lost": True}))
        self.assertEqual(cm.CONFIG_FILE.read_bytes(), before)
        self.assertEqual(list(cm.CONFIG_DIR.glob("*.tmp")), [], "no stray copy of the keys")
        self.assertIn("config_manager.write", {n["where"] for n in failures.recent()})

    def test_a_value_json_cannot_hold_is_refused_not_raised(self):
        # An exception here would escape a Qt slot, and PyQt6 aborts on that.
        before = cm.CONFIG_FILE.read_bytes()
        with _quiet():
            cm._patch_config(not_json={1, 2, 3})
        self.assertEqual(cm.CONFIG_FILE.read_bytes(), before)
        self.assertEqual(list(cm.CONFIG_DIR.glob("*.tmp")), [])

    def test_nothing_is_written_when_the_block_raises(self):
        before = cm.CONFIG_FILE.read_bytes()
        with self.assertRaises(RuntimeError):
            with cm._config_txn() as data:
                data["half_done"] = True
                raise RuntimeError("the setter failed part-way")
        self.assertEqual(cm.CONFIG_FILE.read_bytes(), before)


class ConcurrentWriters(WithATemporaryConfig):
    def setUp(self):
        super().setUp()
        failures.clear()
        self.write_settings(dict(SECRETS))

    def run_threads(self, target, count):
        threads = [threading.Thread(target=target, args=(n,)) for n in range(count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        self.assertFalse(any(t.is_alive() for t in threads), "a writer is stuck")

    def test_concurrent_setters_lose_nothing(self):
        # Measured before the fix: 175 of 200 writes were lost.
        def worker(n):
            for i in range(25):
                cm._patch_config(**{f"k_{n}_{i}": i})

        with _quiet():
            self.run_threads(worker, 8)
        saved = self.read_settings()
        present = sum(1 for k in saved if k.startswith("k_"))
        self.assertEqual(present, 200)
        self.assertEqual(saved["gemini_api_key"], SECRETS["gemini_api_key"])
        self.assertEqual(list(cm.CONFIG_DIR.glob("*.tmp")), [])

    def test_a_burst_of_tool_calls_keeps_the_keys_and_counts_every_call(self):
        # The live trigger: tool_usage.note() saves on every call, on worker
        # threads. Before the fix: keys gone in 3 runs of 3, 4-26 of 320 counted,
        # torn JSON visible to readers.
        stop = threading.Event()
        torn = []
        refused = []

        def reader():
            while not stop.is_set():
                try:
                    json.loads(cm.CONFIG_FILE.read_text(encoding="utf-8"))
                except (FileNotFoundError, PermissionError) as error:
                    refused.append(type(error).__name__)   # Windows refuses a read mid-replace
                except ValueError as error:
                    torn.append(repr(error))

        def worker(n):
            for _ in range(40):
                tool_usage.note(f"tool_{n}")

        watcher = threading.Thread(target=reader)
        watcher.start()
        try:
            with _quiet():
                self.run_threads(worker, 8)
        finally:
            stop.set()
            watcher.join(timeout=10)
        saved = self.read_settings()
        counted = sum(row["count"] for row in saved["tool_usage"].values())
        self.assertEqual(counted, 320, "every tool call must be counted exactly once")
        self.assertEqual(saved["gemini_api_key"], SECRETS["gemini_api_key"])
        self.assertIn("providers", saved)
        self.assertEqual(torn, [], "a reader must never see a half-written file")
        self.assertEqual(list(cm.CONFIG_DIR.glob("*.broken-*")), [])

    def test_provider_setters_do_not_overwrite_each_other(self):
        # They read the providers block OUTSIDE the lock and wrote it back whole,
        # so a stale copy erased whatever another setter had just stored.
        def creds_writer(_n):
            for i in range(30):
                cm.save_provider_config(f"openai_compat@p{i}", {"api_key": f"k{i}"})

        def pipeline_writer(_n):
            for i in range(30):
                cm.save_pipeline(llm=f"openai_compat@p{i}")

        threads = [threading.Thread(target=creds_writer, args=(0,)),
                   threading.Thread(target=pipeline_writer, args=(1,))]
        with _quiet():
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60)
        block = self.read_settings()["providers"]
        self.assertEqual(len(block["creds"]), 30 + 1, "all 30 new services plus groq")
        self.assertEqual(block["pipeline"]["llm"], "openai_compat@p29")


class FirstRunTellsTheTruth(WithATemporaryConfig):
    def setUp(self):
        super().setUp()
        failures.clear()

    def test_a_refused_write_raises_so_the_screen_can_say_so(self):
        # MainWindow reports an exception on screen and otherwise assumes "saved".
        self.write_settings(dict(SECRETS))
        with mock.patch.object(Path, "read_bytes", _locked_read(Path.read_bytes)), _quiet():
            with self.assertRaises(OSError):
                cm.apply_first_run(os_name="windows", gemini_api_key="AIza-new-key-00000")
        self.assertEqual(self.read_settings()["gemini_api_key"], SECRETS["gemini_api_key"])

    def test_a_failed_write_raises_too(self):
        with mock.patch.object(cm.os, "replace", side_effect=OSError("disk full")), _quiet():
            with self.assertRaises(OSError):
                cm.apply_first_run(os_name="windows", gemini_api_key="AIza-new-key-00000")

    def test_a_good_save_returns_what_is_on_disk(self):
        self.write_settings(dict(SECRETS))
        cfg = cm.apply_first_run(os_name="windows", gemini_api_key="AIza-new-key-00000")
        self.assertEqual(cfg, self.read_settings())
        self.assertEqual(cfg["os_system"], "windows")
        self.assertIn("openai_compat@groq", cfg["providers"]["creds"], "kept what was there")


class ScreenProcessorUsesTheLockedSetter(WithATemporaryConfig):
    def test_saving_a_vision_key_keeps_the_other_settings(self):
        self.write_settings(dict(SECRETS))
        try:
            from actions import screen_processor
        except ImportError as error:          # a GUI/system library missing on this machine
            self.skipTest(f"actions.screen_processor needs a library that is absent: {error}")
        with _quiet():
            screen_processor._save_config_key("vision_note", "x")
        saved = self.read_settings()
        self.assertEqual(saved["vision_note"], "x")
        self.assertEqual(saved["gemini_api_key"], SECRETS["gemini_api_key"])


if __name__ == "__main__":
    unittest.main()
