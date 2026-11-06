"""Offline tests for the rename to Ultron and the spoken-register pass.

Two claims are under test:
  * the assistant knows its own name, and the name is defined in ONE place;
  * text leaves the machine as speech rather than as a document.
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from core import identity, voice_style

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "core" / "prompt.txt"


class IdentityTests(unittest.TestCase):
    def test_the_name_is_ultron(self):
        self.assertEqual(identity.NAME, "Ultron")
        self.assertEqual(identity.display_name(), "Ultron")

    def test_it_answers_to_the_old_names_without_correcting(self):
        for name in ("JARVIS", "Jarvis", "Mark", "Ultron"):
            self.assertTrue(identity.is_self_name(name), name)
        self.assertFalse(identity.is_self_name("Spotify"))

    def test_being_addressed_is_detected(self):
        for phrase in ("Hey Ultron, open notes", "ultron?", "Okay Jarvis, stop"):
            self.assertTrue(identity.is_being_addressed(phrase), phrase)
        self.assertFalse(identity.is_being_addressed("open the notes app"))

    def test_upstream_attribution_is_still_recorded(self):
        facts = identity.as_facts()
        self.assertIn("MARK LVI", facts["upstream"])
        self.assertIn("CC BY-NC", facts["license"])

    def test_config_defaults_come_from_the_identity_module(self):
        from memory import config_manager

        with patch.object(config_manager, "load_api_keys", return_value={}):
            self.assertEqual(config_manager.get_assistant_name(), identity.NAME)


class PromptIdentityTests(unittest.TestCase):
    def setUp(self):
        self.text = PROMPT.read_text(encoding="utf-8-sig")

    def test_the_name_token_is_still_injected(self):
        self.assertIn("{assistant_name}", self.text)

    def test_the_prompt_names_the_project(self):
        self.assertIn("Ultron", self.text)

    def test_the_manner_section_exists(self):
        self.assertIn("[MANNER]", self.text)

    def test_the_speech_rules_that_matter_are_present(self):
        lowered = self.text.lower()
        self.assertIn("no bullet points", lowered)
        self.assertIn("no preamble", lowered)
        self.assertIn("sir", lowered)

    def test_the_persona_does_not_regress_into_chatbot_language(self):
        """The prompt must forbid the tells, not merely omit permission for them."""
        lowered = self.text.lower()
        self.assertIn("certainly", lowered)      # named as forbidden
        self.assertIn("great question", lowered)

    def test_no_stale_jarvis_branding_in_the_addendum_heading(self):
        self.assertNotIn("CUSTOM JARVIS SAFETY ADDENDUM", self.text)
        self.assertIn("CUSTOM ULTRON SAFETY ADDENDUM", self.text)


class VoiceStyleTests(unittest.TestCase):
    def test_markdown_emphasis_is_removed(self):
        self.assertEqual(voice_style.spoken("**Disk:** 41 GB free"), "Disk: 41 GB free")
        self.assertEqual(voice_style.spoken("__Really__ fine"), "Really fine")

    def test_code_ticks_and_headings_are_removed(self):
        self.assertEqual(voice_style.spoken("## Status"), "Status")
        self.assertEqual(voice_style.spoken("Run `setup.py` now"), "Run setup.py now")

    def test_a_bullet_list_becomes_sentences(self):
        spoken = voice_style.spoken("Steps:\n- Check the drive\n- Copy the file")
        self.assertNotIn("-", spoken)
        self.assertIn("Check the drive.", spoken)
        self.assertIn("Copy the file.", spoken)

    def test_numbered_lists_are_flattened_too(self):
        spoken = voice_style.spoken("1. Check the drive\n2. Copy the file")
        self.assertNotIn("1.", spoken)
        self.assertIn("Check the drive.", spoken)

    def test_stacked_openers_are_all_dropped(self):
        self.assertEqual(voice_style.spoken("Sure! Certainly, the drive has 41 GB free."),
                         "the drive has 41 GB free.")

    def test_a_complete_short_answer_is_never_deleted(self):
        self.assertEqual(voice_style.spoken("Sure."), "Sure.")
        self.assertEqual(voice_style.spoken("Yes."), "Yes.")

    def test_content_is_not_rewritten(self):
        text = "The file is at C:\\Users\\me\\notes.txt and holds 41 lines."
        self.assertEqual(voice_style.spoken(text), text)

    def test_links_keep_their_text(self):
        self.assertEqual(voice_style.spoken("See [the docs](https://example.com)"),
                         "See the docs")

    def test_written_register_detection(self):
        self.assertTrue(voice_style.is_written_register("## a\n- b"))
        self.assertFalse(voice_style.is_written_register("The drive has 41 GB free."))

    def test_empty_input_is_safe(self):
        for value in ("", None, "   "):
            self.assertEqual(voice_style.spoken(value), "")


class PipelineSpeechTests(unittest.TestCase):
    def test_the_tts_path_flattens_lists_and_drops_emoji(self):
        from providers.engine_pipeline import _speakable

        text = "**Sure!** Here you go:\n- one\n- two \u2600"
        result = _speakable(text)
        self.assertNotIn("*", result)
        self.assertNotIn("-", result)
        self.assertNotIn("\u2600", result)
        self.assertIn("one.", result)

    def test_plain_speech_passes_through(self):
        from providers.engine_pipeline import _speakable

        self.assertEqual(_speakable("The drive has 41 GB free."),
                         "The drive has 41 GB free.")


if __name__ == "__main__":
    unittest.main()
