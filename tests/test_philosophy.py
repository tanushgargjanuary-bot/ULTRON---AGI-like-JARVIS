"""The minds Ultron thinks with, and the three things that make them safe.

    a voice is text        nothing in the cast is executable; every "ability" is a
                           method for using a tool that already exists;
    a voice states a bound every voice says what it may never do, in the same breath
                           as its maxim, and the bound is rendered into the prompt;
    a voice cannot escalate the adversary voice is held under 40% of the mind, the
                           blend is capped at three voices, and the block that
                           carries them says that permission is not for sale.

Everything that writes runs against a throwaway `api_keys.json`. A test that changed
the real config would leave the repository changed by a test run.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import philosophy
from memory import config_manager as cm


try:                                       # discovered from the tests folder
    from tempconfig import WithATemporaryConfig
except ImportError:                        # imported as tests.test_philosophy
    from tests.tempconfig import WithATemporaryConfig


class TheCast(unittest.TestCase):
    def test_every_voice_says_what_it_thinks_by(self):
        for key, voice in philosophy.VOICES.items():
            with self.subTest(voice=key):
                self.assertTrue(voice.name and voice.source)
                self.assertTrue(voice.maxim.endswith("."), voice.maxim)
                self.assertTrue(voice.stance.endswith("."), voice.stance)

    def test_every_voice_states_a_bound(self):
        # The rule this project cannot lose: a voice arrives with its own limit.
        for key, voice in philosophy.VOICES.items():
            with self.subTest(voice=key):
                self.assertTrue(voice.bound.strip())
                low = voice.bound.lower()
                self.assertTrue(any(word in low for word in ("never", "not ", "no ")),
                                f"{key} states no limit: {voice.bound}")

    def test_every_voice_brings_a_method_or_two(self):
        for key, voice in philosophy.VOICES.items():
            with self.subTest(voice=key):
                self.assertGreaterEqual(len(voice.moves), 2)
                for move in voice.moves:
                    name, _, instruction = move.partition(":")
                    self.assertTrue(name and instruction, move)

    def test_a_method_is_words_not_a_permission(self):
        # Nothing in the cast may claim to run by itself or skip a confirmation.
        banned = ("without asking", "without confirmation", "unattended",
                  "automatically", "no permission needed")
        for voice in philosophy.VOICES.values():
            for move in voice.moves:
                for phrase in banned:
                    self.assertNotIn(phrase, move.lower(),
                                     f"{voice.key} claims an unattended power")

    def test_the_names_the_owner_will_say_all_resolve(self):
        for said, expected in (("Rick", "rick"), ("rick sanchez", "rick"),
                               ("Tony Stark", "stark"), ("iron man", "stark"),
                               ("the villain", "ultron"), ("Robot", "robot"),
                               ("HAL 9000", "hal"), ("Data", "data"),
                               ("Jarvis", "jarvis"), ("the butler", "jarvis")):
            with self.subTest(said=said):
                self.assertEqual(philosophy.resolve(said), expected)

    def test_a_name_it_does_not_have_resolves_to_nothing(self):
        self.assertIsNone(philosophy.resolve("Bender"))
        self.assertIsNone(philosophy.resolve(""))

    def test_long_names_are_read_before_short_ones(self):
        spellings = [spelling for spelling, _key in philosophy.spellings()]
        self.assertLess(spellings.index("hal 9000"), spellings.index("hal"))


class TheBlend(WithATemporaryConfig):
    def test_the_default_mind_is_valid_and_small(self):
        default = philosophy.DEFAULT_BLEND
        self.assertLessEqual(len(default), philosophy.MAX_VOICES)
        self.assertAlmostEqual(sum(default.values()), 1.0, places=2)
        self.assertIn("jarvis", default)

    def test_a_chosen_mind_is_kept_in_the_settings_file(self):
        chosen, notes = philosophy.save_blend({"stark": 0.6, "data": 0.4})
        self.assertEqual(notes, [])
        self.assertEqual(set(chosen), {"stark", "data"})
        self.assertEqual(philosophy.blend(), chosen)
        self.assertIn("philosophy", self.read_settings())

    def test_a_damaged_setting_falls_back_to_the_shipped_mind(self):
        self.write_settings({"philosophy": "not an object"})
        self.assertEqual(philosophy.blend(), philosophy.DEFAULT_BLEND)

    def test_reset_returns_the_shipped_mind(self):
        philosophy.save_blend({"robot": 1.0})
        self.assertEqual(philosophy.reset(), philosophy.DEFAULT_BLEND)
        self.assertEqual(philosophy.blend(), philosophy.DEFAULT_BLEND)

    def test_the_shares_read_as_whole_percentages(self):
        philosophy.save_blend({"jarvis": 0.5, "stark": 0.3, "data": 0.2})
        line = philosophy.shares()
        self.assertIn("50%", line)
        total = sum(weight for _key, weight in philosophy.shares_of(philosophy.blend()))
        self.assertAlmostEqual(total, 1.0, places=2)


class TheCeilings(WithATemporaryConfig):
    def test_the_adversary_cannot_be_the_whole_mind(self):
        chosen, notes = philosophy.save_blend({"ultron": 0.9})
        self.assertLessEqual(chosen["ultron"], philosophy.VOICES["ultron"].ceiling)
        self.assertIn("jarvis", chosen)
        self.assertAlmostEqual(sum(chosen.values()), 1.0, places=2)
        self.assertTrue(any("held at" in note for note in notes), notes)

    def test_the_scientist_is_capped_too(self):
        chosen, _notes = philosophy.save_blend({"rick": 1.0})
        self.assertLessEqual(chosen["rick"], philosophy.VOICES["rick"].ceiling)
        self.assertAlmostEqual(sum(chosen.values()), 1.0, places=2)

    def test_a_share_written_as_a_percentage_is_understood(self):
        chosen, _notes = philosophy.save_blend({"stark": 40, "data": 60})
        self.assertAlmostEqual(chosen["stark"], 0.4, places=2)

    def test_a_negative_share_is_ignored_and_said_so(self):
        chosen, notes = philosophy.save_blend({"stark": -1, "jarvis": 1})
        self.assertNotIn("stark", chosen)
        self.assertTrue(any("negative" in note for note in notes), notes)

    def test_a_share_too_faint_to_matter_is_dropped(self):
        chosen, notes = philosophy.save_blend({"jarvis": 0.99, "data": 0.01})
        self.assertNotIn("data", chosen)
        self.assertTrue(any("too faint" in note for note in notes), notes)

    def test_only_three_voices_are_kept_and_the_others_are_named(self):
        chosen, notes = philosophy.save_blend(
            {"jarvis": 0.25, "stark": 0.25, "data": 0.25, "robot": 0.25})
        self.assertEqual(len(chosen), philosophy.MAX_VOICES)
        self.assertTrue(any("left out" in note for note in notes), notes)

    def test_a_name_it_does_not_have_is_reported_not_obeyed(self):
        _chosen, notes = philosophy.save_blend({"bender": 0.5})
        self.assertTrue(any("not one of the minds" in note for note in notes), notes)


class ThePromptBlock(WithATemporaryConfig):
    def test_the_block_opens_with_its_heading_and_the_charter(self):
        block = philosophy.prompt_block()
        self.assertTrue(block.startswith(philosophy.HEADER))
        self.assertIn(philosophy.CHARTER, block)
        self.assertIn(philosophy.TIE_BREAK, block)

    def test_every_voice_in_the_blend_appears_with_its_bound(self):
        philosophy.save_blend({"jarvis": 0.5, "stark": 0.3, "data": 0.2})
        block = philosophy.prompt_block()
        for key in ("jarvis", "stark", "data"):
            voice = philosophy.VOICES[key]
            self.assertIn(voice.name, block)
            self.assertIn(voice.bound, block)

    def test_a_voice_out_of_the_blend_is_not_in_the_instruction(self):
        philosophy.save_blend({"jarvis": 0.6, "stark": 0.4})
        block = philosophy.prompt_block()
        self.assertNotIn(philosophy.VOICES["ultron"].name, block)
        self.assertNotIn(philosophy.VOICES["rick"].name, block)

    def test_the_added_text_stays_small(self):
        # Paid for on every request. Measured at about 1,000 characters for three.
        philosophy.save_blend({"jarvis": 0.4, "stark": 0.3, "data": 0.3})
        self.assertLess(len(philosophy.prompt_block()), 1_500)

    def test_no_mind_means_no_block(self):
        self.assertEqual(philosophy.prompt_block({}), "")

    def test_the_readers_show_it_too(self):
        # "Show me your prompt" has to mean the whole of it, not the file alone.
        from actions import prompt_editor
        self.assertIn("[PHILOSOPHY", prompt_editor._show())


class TheTool(WithATemporaryConfig):
    @classmethod
    def setUpClass(cls):
        from actions import philosophy as tool
        cls.tool = tool

    def call(self, **parameters) -> str:
        return self.tool.philosophy_tool(parameters)

    def test_every_action_name_reaches_a_callable(self):
        for name in self.tool.ACTIONS:
            with self.subTest(action=name):
                self.assertTrue(callable(self.tool.ACTIONS[name]))

    def test_the_declaration_is_what_the_loader_expects(self):
        declaration = self.tool.TOOL
        self.assertEqual(declaration["name"], "philosophy")
        self.assertTrue(callable(declaration["handler"]))
        self.assertEqual(declaration["parameters"]["type"], "OBJECT")
        offered = set(declaration["parameters"]["properties"]["action"]["enum"])
        self.assertTrue(offered <= set(self.tool.ACTIONS))

    def test_an_unknown_action_says_what_it_can_do(self):
        answer = self.call(action="levitate")
        self.assertIn("levitate", answer)
        self.assertIn("blend", answer)

    def test_show_names_the_mind_in_force(self):
        philosophy.save_blend({"stark": 1.0})
        self.assertIn("Tony Stark", self.call(action="show"))

    def test_adopting_a_mind_changes_it(self):
        answer = self.call(action="adopt", voice="the robot from invincible")
        self.assertIn("Robot", answer)
        self.assertIn("robot", philosophy.blend())

    def test_adopting_a_mind_it_does_not_have_changes_nothing(self):
        before = philosophy.blend()
        answer = self.call(action="adopt", voice="Sherlock")
        self.assertIn("Sherlock", answer)
        self.assertIn("Rick Sanchez", answer)
        self.assertEqual(philosophy.blend(), before)

    def test_the_three_ways_an_owner_says_a_mix_agree(self):
        # Name-then-number, and number-with-a-percent-then-name. Both are how people
        # say it, and both have to mean the same thing.
        expected = {"rick": 40.0, "stark": 60.0}
        for said in ("rick 40 stark 60", "rick=40, stark=60", "40% Rick and 60% Stark",
                     "Rick 40, Stark 60"):
            with self.subTest(said=said):
                self.assertEqual(self.tool._parse_weights(said), expected)

    def test_a_percent_sign_does_not_move_the_number(self):
        self.assertEqual(self.tool._parse_weights("60% Rick and 40% Stark"),
                         {"rick": 60.0, "stark": 40.0})

    def test_a_mix_with_no_mind_in_it_is_refused(self):
        before = philosophy.blend()
        self.assertIn("could not find", self.call(action="blend", weights="banana 50"))
        self.assertEqual(philosophy.blend(), before)

    def test_a_mix_given_as_a_sentence_still_lands(self):
        self.call(action="blend", weights="be 30% Rick, 70% Jarvis")
        self.assertEqual(set(philosophy.blend()), {"rick", "jarvis"})

    def test_abilities_lists_the_methods_of_one_mind(self):
        answer = self.call(action="abilities", voice="stark")
        for move in philosophy.VOICES["stark"].moves:
            self.assertIn(move.split(":", 1)[0], answer)
        self.assertIn("not a permission", answer)

    def test_abilities_of_every_mind_are_listed(self):
        answer = self.call(action="abilities")
        for voice in philosophy.VOICES.values():
            self.assertIn(voice.name.split(" ")[0], answer)

    def test_the_rules_state_the_ceiling(self):
        self.assertIn("40%", self.call(action="rules"))

    def test_the_cast_lists_every_voice(self):
        answer = self.call(action="list")
        for voice in philosophy.VOICES.values():
            self.assertIn(voice.name, answer)

    def test_an_error_is_a_sentence_not_a_crash(self):
        # A share that cannot be a number must be answered, not raised.
        answer = self.call(action="adopt", voice="stark", weight="a lot")
        self.assertIsInstance(answer, str)
        self.assertTrue(answer)


if __name__ == "__main__":
    unittest.main()
