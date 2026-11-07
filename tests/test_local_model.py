"""Offline checks for the local-model helper.

Every test here runs with no server and no model on disk. The point of the script is to say
what this machine can run and what it cannot, so the checks are about the decision and the
file it writes, not about a download.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import local_model as lm


class Recommendation(unittest.TestCase):
    """The suggested model must follow the memory, not the wish."""

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

    def test_an_unknown_machine_still_gets_an_answer(self):
        model, why = lm.recommend(0.0, 0.0)
        self.assertEqual(model, "llama3.2:3b")
        self.assertIn("memory unknown", why)

    def test_an_enormous_machine_is_capped(self):
        model, _ = lm.recommend(256.0, 24.0)
        self.assertEqual(model, "qwen2.5-coder:32b")


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
