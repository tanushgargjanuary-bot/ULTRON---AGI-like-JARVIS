"""Offline checks for the local-model helper.

Every test here runs with no server and no model on disk. The point of the script is to say
what this machine can run and what it cannot, so the checks are about the decision and the
file it writes, not about a download.
"""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import local_model as lm


class Recommendation(unittest.TestCase):
    """The suggested model must follow the memory, not the wish."""

    def test_a_tiny_machine_gets_the_edge_model(self):
        model, why = lm.recommend(4.0, 0.0)
        self.assertEqual(model, "lfm2:1.2b")
        self.assertIn("900 MB", why)

    def test_a_small_machine_gets_a_small_model(self):
        model, why = lm.recommend(8.0, 0.0)
        self.assertEqual(model, "llama3.2:3b")
        self.assertIn("8 GB", why)

    def test_a_midrange_desktop_gets_the_coder_model(self):
        model, _ = lm.recommend(16.0, 0.0)
        self.assertEqual(model, "qwen2.5-coder:7b")

    def test_graphics_memory_counts_towards_the_budget(self):
        small, _ = lm.recommend(8.0, 0.0)
        large, why = lm.recommend(8.0, 8.0)
        self.assertNotEqual(small, large)
        self.assertIn("graphics card", why)

    def test_an_unknown_machine_gets_the_model_that_runs_anywhere(self):
        model, why = lm.recommend(0.0, 0.0)
        self.assertEqual(model, "lfm2:1.2b")
        self.assertIn("memory unknown", why)

    def test_an_enormous_machine_is_capped(self):
        model, _ = lm.recommend(256.0, 24.0)
        self.assertEqual(model, "qwen2.5-coder:32b")


class Bench(unittest.TestCase):
    """The bench must be readable, and a wrong answer must score as wrong."""

    def test_a_marker_in_any_case_counts(self):
        self.assertTrue(lm.score_reply(("ready",), "READY."))
        self.assertFalse(lm.score_reply(("ready",), "I am not sure what you mean."))

    def test_an_empty_answer_never_passes(self):
        self.assertFalse(lm.score_reply(("ready",), ""))

    def test_the_bench_has_three_jobs_and_each_has_a_marker(self):
        self.assertEqual(len(lm.BENCH_TASKS), 3)
        for name, prompt, expected in lm.BENCH_TASKS:
            self.assertTrue(name and prompt and expected)

    def test_the_summary_counts_passes_and_seconds(self):
        rows = [
            {"task": "chat", "ok": True, "seconds": 0.5, "text": "ready", "error": ""},
            {"task": "edit", "ok": False, "seconds": 1.5, "text": "no", "error": ""},
        ]
        lines = lm.bench_lines(rows)
        self.assertIn("1 of 2 passed", lines[-1])
        self.assertIn("2.0s", lines[-1])


class ServerAndConfig(unittest.TestCase):
    """A server that is down is a fact to report, not an exception to raise."""

    def test_a_dead_server_reports_no_models(self):
        self.assertEqual(lm.installed_models("http://127.0.0.1:9"), [])

    def test_asking_a_dead_server_returns_an_error_not_a_crash(self):
        answer = lm.ask("http://127.0.0.1:9", "anything")
        self.assertFalse(answer["ok"])
        self.assertTrue(answer["error"])

    def test_the_three_keys_are_the_ones_the_app_reads(self):
        keys = lm.config_lines("http://localhost:11434", "llama3.2:3b")
        self.assertEqual(set(keys), {"llm_provider", "llm_url", "llm_model"})
        self.assertEqual(keys["llm_provider"], "ollama")

    def test_writing_keeps_the_keys_the_owner_pasted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            path.write_text(json.dumps({"gemini_key": "keep-me"}), encoding="utf-8")

            backup = lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
            written = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(written["gemini_key"], "keep-me")
            self.assertEqual(written["llm_model"], "llama3.2:3b")
            self.assertTrue(backup.exists())
            self.assertIn("keep-me", backup.read_text(encoding="utf-8"))

    def test_a_config_that_cannot_be_read_is_refused_not_replaced(self):
        # It used to be read as {} and written back as the three local-model keys alone,
        # which removed the owner's Gemini and provider keys.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            damaged = b'{"gemini_api_key": "keep-me", "providers": {"cre'
            path.write_bytes(damaged)
            with self.assertRaises(ValueError):
                lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
            self.assertEqual(path.read_bytes(), damaged)
            self.assertFalse(path.with_suffix(".json.bak").exists())
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])

    def test_the_command_says_so_instead_of_a_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            path.write_text("[1, 2]", encoding="utf-8")
            with patch.object(lm, "total_memory_gb", return_value=16.0), \
                 patch.object(lm, "graphics_memory_gb", return_value=0.0), \
                 patch.object(lm, "installed_models", return_value=[]):
                code = lm.main(["write", "--config", str(path), "--yes"])
            self.assertEqual(code, 1)
            self.assertEqual(path.read_text(encoding="utf-8"), "[1, 2]")

    def test_a_store_saved_with_a_byte_order_mark_is_merged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"gemini_key": "keep-me"}).encode())
            lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["gemini_key"], "keep-me")

    def test_an_interrupted_write_leaves_the_old_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            path.write_text(json.dumps({"gemini_key": "keep-me"}), encoding="utf-8")
            before = path.read_bytes()
            with patch.object(lm.os, "replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])

    @unittest.skipIf(os.name == "nt", "file modes are a POSIX idea; Windows uses ACLs")
    def test_the_key_file_stays_owner_only_after_a_write(self):
        # The temporary file used to be created with the default mode and renamed over the key file,
        # so a 0600 file came out 0644 and every other user of the machine could read the keys.
        previous = os.umask(0o022)
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "api_keys.json"
                path.write_text(json.dumps({"gemini_key": "keep-me"}), encoding="utf-8")
                os.chmod(path, 0o600)
                backup = lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600, "the copy holds the keys too")
        finally:
            os.umask(previous)

    @unittest.skipIf(os.name == "nt", "file modes are a POSIX idea; Windows uses ACLs")
    def test_a_config_created_by_the_command_is_owner_only(self):
        previous = os.umask(0o022)
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "api_keys.json"
                lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        finally:
            os.umask(previous)

    @unittest.skipIf(os.name == "nt", "file modes are a POSIX idea; Windows uses ACLs")
    def test_the_temporary_file_is_owner_only_for_as_long_as_it_exists(self):
        seen = []
        real = os.replace

        def spy(source, target):
            seen.append(stat.S_IMODE(os.stat(source).st_mode))
            return real(source, target)

        previous = os.umask(0o022)
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "api_keys.json"
                with patch.object(lm.os, "replace", side_effect=spy):
                    lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
        finally:
            os.umask(previous)
        self.assertEqual(seen, [0o600])

    def test_the_temporary_file_has_a_name_of_its_own(self):
        # Two writers must never share one: a fixed `api_keys.json.tmp` was one file for both.
        names = []
        real = os.replace

        def spy(source, target):
            names.append(Path(source).name)
            return real(source, target)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            for _ in range(2):
                with patch.object(lm.os, "replace", side_effect=spy):
                    lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
        self.assertEqual(len(set(names)), 2, names)
        for name in names:
            self.assertTrue(name.startswith("api_keys.json.") and name.endswith(".tmp"), name)

    @unittest.skipIf(os.name == "nt", "file modes are a POSIX idea; Windows uses ACLs")
    def test_the_backup_of_a_loosely_protected_key_file_is_owner_only(self):
        # shutil.copy2 gave the backup the original's mode: a 0644 key file made a 0644 backup of the
        # same keys. (The new main file was 0600 by then; the backup was the leak.)
        previous = os.umask(0o022)
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "api_keys.json"
                path.write_text(json.dumps({"gemini_key": "keep-me"}), encoding="utf-8")
                os.chmod(path, 0o644)
                before = path.read_bytes()
                backup = lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
                self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(backup.read_bytes(), before, "the backup is the file as it was")
        finally:
            os.umask(previous)

    @unittest.skipIf(os.name == "nt", "file modes are a POSIX idea; Windows uses ACLs")
    def test_a_loose_backup_left_by_an_earlier_run_is_replaced_by_a_private_one(self):
        previous = os.umask(0o022)
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "api_keys.json"
                backup = Path(folder) / "api_keys.json.bak"
                backup.write_text("stale", encoding="utf-8")
                os.chmod(backup, 0o644)
                path.write_text(json.dumps({"gemini_key": "keep-me"}), encoding="utf-8")
                lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
                self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
                self.assertIn("keep-me", backup.read_text(encoding="utf-8"))
                self.assertNotIn("stale", backup.read_text(encoding="utf-8"))
        finally:
            os.umask(previous)

    @unittest.skipIf(os.name == "nt", "file modes are a POSIX idea; Windows uses ACLs")
    def test_the_backup_is_owner_only_while_the_keys_are_being_copied_in(self):
        seen = []
        real = lm.shutil.copyfileobj

        def spy(source, target, *args):
            seen.append(stat.S_IMODE(os.fstat(target.fileno()).st_mode))
            return real(source, target, *args)

        previous = os.umask(0o022)
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "api_keys.json"
                path.write_text(json.dumps({"gemini_key": "keep-me"}), encoding="utf-8")
                os.chmod(path, 0o644)
                with patch.object(lm.shutil, "copyfileobj", side_effect=spy):
                    lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
        finally:
            os.umask(previous)
        self.assertEqual(seen, [0o600], "the file was open to others while the keys went in")

    def test_the_backup_keeps_the_originals_modification_time(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            path.write_text(json.dumps({"gemini_key": "keep-me"}), encoding="utf-8")
            os.utime(path, (1_600_000_000, 1_600_000_000))
            backup = lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
            self.assertEqual(int(backup.stat().st_mtime), 1_600_000_000)

    def test_a_backup_that_cannot_be_completed_stops_the_write_and_leaves_nothing_behind(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            path.write_text(json.dumps({"gemini_key": "keep-me"}), encoding="utf-8")
            before = path.read_bytes()
            with patch.object(lm.shutil, "copyfileobj", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
            self.assertEqual(path.read_bytes(), before, "the keys were rewritten with no backup")
            self.assertFalse((Path(folder) / "api_keys.json.bak").exists(), "a half-written backup was left")
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])

    def test_a_missing_config_is_created_rather_than_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nested" / "api_keys.json"
            lm.write_config(path, "http://localhost:11434", "llama3.2:3b")
            self.assertTrue(path.exists())


class CommandLine(unittest.TestCase):
    """``check`` must never write anything, and must never need a model."""

    def test_check_reports_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            with patch.object(lm, "total_memory_gb", return_value=16.0), \
                 patch.object(lm, "graphics_memory_gb", return_value=0.0), \
                 patch.object(lm, "installed_models", return_value=[]):
                code = lm.main(["check", "--config", str(path)])
            self.assertEqual(code, 0)
            self.assertFalse(path.exists())

    def test_pull_without_ollama_explains_what_to_install(self):
        with patch.object(lm, "total_memory_gb", return_value=16.0), \
             patch.object(lm, "graphics_memory_gb", return_value=0.0), \
             patch.object(lm, "installed_models", return_value=[]), \
             patch.object(lm, "ollama_present", return_value=False):
            self.assertEqual(lm.main(["pull"]), 1)


if __name__ == "__main__":
    unittest.main()
