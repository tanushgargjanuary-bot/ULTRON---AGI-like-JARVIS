"""tests/test_first_run.py — what the first-run screen writes, and what it must not.

Two defects are pinned here.

1. `_on_setup_done` wrote `{"gemini_api_key": ..., "os_system": ...}` straight over
   api_keys.json. Re-opening setup — which the app does by itself when a key is
   rejected — erased the assistant's name, voice, colour, interface scale and
   every configured provider. A settings screen that resets your settings.

2. `_check_config` demanded `gemini_api_key`, so an install configured with Ollama
   or Groq was sent back to first-run every launch, and the setup screen offered
   no way to configure anything but Gemini.

`apply_first_run` and `is_configured` are the fix, and they are plain functions
so that these can be ordinary tests rather than screenshots.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from memory import config_manager as cm


class ConfigSandbox(unittest.TestCase):
    """Point the config module at a throwaway api_keys.json for each test."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.dir = Path(self._temp.name)
        self._saved = (cm.CONFIG_DIR, cm.CONFIG_FILE)
        cm.CONFIG_DIR = self.dir
        cm.CONFIG_FILE = self.dir / "api_keys.json"

    def tearDown(self):
        cm.CONFIG_DIR, cm.CONFIG_FILE = self._saved
        self._temp.cleanup()

    def write(self, payload: dict) -> None:
        cm.CONFIG_FILE.write_text(json.dumps(payload), encoding="utf-8")

    def read(self) -> dict:
        return json.loads(cm.CONFIG_FILE.read_text(encoding="utf-8"))


class NothingIsLostTests(ConfigSandbox):
    def test_reopening_setup_keeps_the_name_voice_colour_and_scale(self):
        self.write({
            "os_system": "windows",
            "gemini_api_key": "old-key",
            "assistant_name": "Ultron",
            "user_name": "Ada",
            "voice_name": "Aoede",
            "ui_color": "#ff8800",
            "ui_scale": 1.45,
        })
        cm.apply_first_run(os_name="windows", gemini_api_key="new-key")
        config = self.read()
        self.assertEqual(config["gemini_api_key"], "new-key")
        for field, value in (("assistant_name", "Ultron"), ("user_name", "Ada"),
                             ("voice_name", "Aoede"), ("ui_color", "#ff8800"),
                             ("ui_scale", 1.45)):
            self.assertEqual(config[field], value, f"{field} was erased by setup")

    def test_a_blank_key_never_deletes_a_stored_one(self):
        self.write({"os_system": "windows", "gemini_api_key": "keep-me"})
        cm.apply_first_run(os_name="windows", gemini_api_key="   ")
        self.assertEqual(self.read()["gemini_api_key"], "keep-me")

    def test_configured_providers_survive_another_run(self):
        self.write({
            "os_system": "windows",
            "gemini_api_key": "k",
            "providers": {"mode": "gemini",
                          "creds": {"openai_compat@groq": {"api_key": "gsk-1",
                                                           "model": "llama-3.3-70b"}}},
        })
        cm.apply_first_run(os_name="windows", providers=[
            {"id": "openai_compat@openai", "values": {"api_key": "sk-2", "model": "gpt-4o"}}
        ])
        creds = self.read()["providers"]["creds"]
        self.assertIn("openai_compat@groq", creds)
        self.assertIn("openai_compat@openai", creds)
        self.assertEqual(creds["openai_compat@groq"]["api_key"], "gsk-1")


class ProviderOnlyTests(ConfigSandbox):
    def test_a_local_provider_alone_makes_an_install_configured(self):
        cm.apply_first_run(os_name="windows", providers=[
            {"id": "openai_compat@ollama",
             "values": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:8b"}}
        ])
        config = self.read()
        self.assertNotIn("gemini_api_key", config)
        self.assertTrue(cm.has_a_brain())

    def test_a_cloud_provider_alone_switches_to_pipeline_mode(self):
        cm.apply_first_run(os_name="windows", providers=[
            {"id": "openai_compat@groq", "values": {"api_key": "gsk", "model": "llama"}}
        ])
        block = self.read()["providers"]
        self.assertEqual(block["mode"], "pipeline")
        self.assertEqual(block["pipeline"]["llm"], "openai_compat@groq")

    def test_a_gemini_key_keeps_the_live_path(self):
        cm.apply_first_run(os_name="windows", gemini_api_key="AIza-x")
        block = self.read().get("providers") or {}
        self.assertNotEqual(block.get("mode"), "pipeline")

    def test_several_providers_are_stored_side_by_side(self):
        cm.apply_first_run(os_name="windows", gemini_api_key="AIza-x", providers=[
            {"id": "openai_compat@groq", "values": {"api_key": "gsk", "model": "llama"}},
            {"id": "openai_compat@ollama",
             "values": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:8b"}},
            {"id": "openai_compat@openrouter", "values": {"api_key": "sk-or", "model": "x"}},
        ])
        creds = self.read()["providers"]["creds"]
        self.assertEqual(len(creds), 3)

    def test_a_provider_with_no_values_is_not_saved(self):
        cm.apply_first_run(os_name="windows", providers=[{"id": "openai_compat@groq",
                                                          "values": {"api_key": "", "model": ""}}])
        creds = (self.read().get("providers") or {}).get("creds") or {}
        self.assertEqual(creds, {})


class IsConfiguredTests(ConfigSandbox):
    def test_a_missing_file_is_not_configured(self):
        self.assertFalse(cm.has_a_brain())

    def test_a_key_without_an_operating_system_is_not_configured(self):
        self.write({"gemini_api_key": "AIza-x"})
        self.assertFalse(cm.has_a_brain())

    def test_a_key_with_an_operating_system_is_configured(self):
        self.write({"gemini_api_key": "AIza-x", "os_system": "windows"})
        self.assertTrue(cm.has_a_brain())

    def test_a_configured_provider_is_configured(self):
        self.write({"os_system": "windows",
                    "providers": {"creds": {"openai_compat@ollama":
                                            {"model": "qwen3:8b"}}}})
        self.assertTrue(cm.has_a_brain())

    def test_an_empty_provider_entry_is_not_configured(self):
        self.write({"os_system": "windows",
                    "providers": {"creds": {"openai_compat@ollama": {"model": ""}}}})
        self.assertFalse(cm.has_a_brain())

    def test_garbage_in_the_providers_block_does_not_raise(self):
        self.write({"os_system": "windows", "providers": ["not", "a", "dict"]})
        self.assertFalse(cm.has_a_brain())


class TheOldNameStillMeansWhatItMeantTests(ConfigSandbox):
    def test_is_configured_still_only_answers_for_gemini(self):
        # Left exactly as it was: callers elsewhere may rely on "a Gemini key is
        # present", and quietly widening it would change their meaning.
        self.write({"os_system": "windows", "gemini_api_key": "short"})
        self.assertFalse(cm.is_configured())
        self.write({"os_system": "windows", "gemini_api_key": "a-long-enough-key-123"})
        self.assertTrue(cm.is_configured())


class PatchSettingsTests(ConfigSandbox):
    def test_it_returns_the_config_it_wrote(self):
        result = cm.patch_settings(os_system="linux")
        self.assertEqual(result["os_system"], "linux")

    def test_it_merges_rather_than_replaces(self):
        self.write({"assistant_name": "Ultron", "voice_name": "Aoede"})
        cm.patch_settings(ui_scale=1.3)
        config = self.read()
        self.assertEqual(config["assistant_name"], "Ultron")
        self.assertEqual(config["ui_scale"], 1.3)


if __name__ == "__main__":
    unittest.main()
