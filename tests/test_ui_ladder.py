"""tests/test_ui_ladder.py — the answer to "what if there is no button tree".

    The user's stated objection to tree-based computer use is exactly right: a
    tree-based agent is only as good as the tree. These tests pin the answer —
    every failure has a next rung, and the last rung is a question rather than a
    guess.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ui_action import UiError
from core.ui_ladder import (
    Context,
    Ladder,
    Rung,
    access_key,
    candidates,
    describe,
    next_step,
)


def err(code, disposition=""):
    return UiError(code, "test", disposition or "fatal")


class FreshLookTests(unittest.TestCase):
    def test_a_stale_ref_means_look_again(self):
        step = next_step(err("STALE_REF"), Context(has_tree=True))
        self.assertEqual(step.rung, Rung.TREE)
        self.assertIn("changed", step.reason)

    def test_a_lost_application_means_look_again(self):
        step = next_step(err("APP_GONE"), Context(has_tree=True))
        self.assertEqual(step.rung, Rung.TREE)

    def test_looking_again_is_not_repeated_forever(self):
        ctx = Context(attempts=2, tried=(Rung.TREE,))
        step = next_step(err("STALE_REF"), ctx)
        self.assertNotEqual(step.rung, Rung.TREE)

    def test_not_ready_is_waited_out_once_then_escalated(self):
        first = next_step(err("NOT_ENABLED"), Context(has_tree=True))
        self.assertEqual(first.rung, Rung.TREE)
        second = next_step(err("NOT_ENABLED"), Context(has_tree=True, attempts=1))
        self.assertEqual(second.rung, Rung.ASK)
        self.assertIn("covering", second.reason)


class AmbiguityTests(unittest.TestCase):
    def test_ambiguity_in_a_truncated_snapshot_is_narrowed_by_drilling(self):
        step = next_step(err("AMBIGUOUS_TARGET"), Context(has_tree=True, truncated=2))
        self.assertEqual(step.rung, Rung.DRILL)

    def test_ambiguity_with_nowhere_to_narrow_asks(self):
        step = next_step(err("AMBIGUOUS_TARGET"), Context(has_tree=True))
        self.assertEqual(step.rung, Rung.ASK)
        self.assertIn("will not pick one", step.reason)


class UnsupportedActionTests(unittest.TestCase):
    def test_a_hotkey_is_preferred_over_anything_that_moves_the_mouse(self):
        step = next_step(err("UNSUPPORTED_ACTION"), Context(has_tree=True, hotkey="alt+s"))
        self.assertEqual(step.rung, Rung.KEYBOARD)
        self.assertEqual(step.hotkey, "alt+s")

    def test_web_content_falls_to_the_dom_before_vision(self):
        step = next_step(err("UNSUPPORTED_ACTION"),
                         Context(has_tree=True, has_dom=True, vision_ready=True))
        self.assertEqual(step.rung, Rung.DOM)

    def test_vision_is_the_last_resort_and_says_so(self):
        step = next_step(err("UNSUPPORTED_ACTION"), Context(has_tree=True, vision_ready=True))
        self.assertEqual(step.rung, Rung.VISION)
        self.assertIn("last resort", step.reason)

    def test_local_ocr_precedes_vision_only_for_a_text_read_request(self):
        ctx = Context(ocr_ready=True, read_text_requested=True, vision_ready=True)
        step = next_step(err("NO_TREE"), ctx)
        self.assertEqual(step.rung, Rung.OCR)
        self.assertIn("cannot click", step.reason)

    def test_ocr_is_not_offered_for_an_action_request(self):
        ctx = Context(ocr_ready=True, vision_ready=True)
        step = next_step(err("NO_TREE"), ctx)
        self.assertEqual(step.rung, Rung.VISION)

    def test_description_reports_local_ocr_state(self):
        text = describe(Context(ocr_ready=True))
        self.assertIn("local OCR available", text)
        self.assertIn("no upload", text)

    def test_with_nothing_left_it_asks(self):
        step = next_step(err("UNSUPPORTED_ACTION"), Context(has_tree=True))
        self.assertEqual(step.rung, Rung.ASK)
        self.assertIn("without guessing", step.reason)


class NoTreeTests(unittest.TestCase):
    def test_a_browser_page_uses_the_page_not_vision(self):
        step = next_step(err("NO_TREE"), Context(dom_only=True, has_dom=True, vision_ready=True))
        self.assertEqual(step.rung, Rung.DOM)
        self.assertIn("page itself", step.reason)

    def test_a_native_app_with_no_tree_tries_the_keyboard(self):
        step = next_step(err("NO_TREE"), Context(keyboard_ready=True))
        self.assertEqual(step.rung, Rung.KEYBOARD)

    def test_no_tree_and_no_keyboard_falls_to_vision_with_a_warning(self):
        step = next_step(err("NO_TREE"), Context(vision_ready=True))
        self.assertEqual(step.rung, Rung.VISION)
        self.assertIn("screenshot", step.reason)

    def test_no_tree_and_no_options_asks_instead_of_clicking(self):
        step = next_step(err("NO_TREE"), Context())
        self.assertEqual(step.rung, Rung.ASK)
        self.assertIn("publishes nothing", step.reason)

    def test_a_thin_tree_with_a_dom_behind_it_uses_the_dom(self):
        step = next_step(None, Context(has_tree=True, tree_nodes=2, has_dom=True))
        self.assertEqual(step.rung, Rung.DOM)

    def test_a_small_dialog_is_not_treated_as_thin(self):
        step = next_step(None, Context(has_tree=True, tree_nodes=2, has_dom=False))
        self.assertEqual(step.rung, Rung.STOP)

    def test_a_missing_adapter_is_a_no_adapter_answer(self):
        step = next_step(err("NO_ADAPTER"), Context(vision_ready=True))
        self.assertEqual(step.rung, Rung.VISION)


class ExhaustionTests(unittest.TestCase):
    def test_with_everything_tried_and_failed_it_stops(self):
        ctx = Context(has_tree=True, has_dom=True, keyboard_ready=True,
                      vision_ready=True, attempts=6,
                      tried=(Rung.TREE, Rung.DRILL, Rung.DOM, Rung.KEYBOARD, Rung.VISION))
        step = next_step(err("ADAPTER_FAILED"), ctx)
        self.assertIn(step.rung, (Rung.ASK, Rung.STOP))

    def test_a_bridge_failure_gets_one_more_look(self):
        step = next_step(err("ADAPTER_FAILED"), Context(has_tree=True, attempts=0))
        self.assertEqual(step.rung, Rung.TREE)

    def test_the_ladder_explains_what_it_tried_without_claiming_success(self):
        ladder = Ladder()
        ladder.record(Rung.TREE, False, "no tree")
        ladder.record(Rung.DOM, False, "not a page")
        sentence = ladder.exhausted()
        self.assertIn("tree", sentence)
        self.assertIn("dom", sentence)
        self.assertNotIn("done", sentence.lower())

    def test_an_empty_ladder_says_it_did_nothing(self):
        self.assertIn("did not try", Ladder().exhausted())

    def test_attempts_and_tried_are_deduplicated(self):
        ladder = Ladder()
        ladder.record(Rung.TREE, False)
        ladder.record(Rung.TREE, False)
        ladder.record(Rung.DOM, True)
        self.assertEqual(ladder.attempts(), 3)
        self.assertEqual(ladder.tried(), (Rung.TREE, Rung.DOM))

    def test_context_from_a_ladder_carries_history(self):
        ladder = Ladder()
        ladder.record(Rung.TREE, False)
        ctx = ladder.context(has_dom=True)
        self.assertEqual(ctx.attempts, 1)
        self.assertTrue(ctx.has_dom)
        self.assertTrue(ctx.tried_already(Rung.TREE))


class AccessKeyTests(unittest.TestCase):
    def test_an_ampersand_marks_the_key(self):
        self.assertEqual(access_key("&Save"), "alt+s")

    def test_capitalisation_does_not_matter(self):
        self.assertEqual(access_key("Save &As..."), "alt+a")

    def test_a_name_without_one_has_no_hotkey(self):
        self.assertEqual(access_key("Save"), "")

    def test_a_trailing_ampersand_is_not_a_key(self):
        self.assertEqual(access_key("Tom &"), "")

    def test_a_digit_key_is_allowed(self):
        self.assertEqual(access_key("Zoom &100%"), "alt+1")

    def test_empty_input_is_safe(self):
        self.assertEqual(access_key(""), "")


class DescribeTests(unittest.TestCase):
    def test_it_names_what_is_reachable(self):
        text = describe(Context(has_tree=True, tree_nodes=12, keyboard_ready=True))
        self.assertIn("accessibility tree (12 elements)", text)
        self.assertIn("keyboard", text)

    def test_it_says_when_vision_is_absent(self):
        self.assertIn("no vision", describe(Context()))

    def test_it_warns_that_vision_sends_a_screenshot(self):
        self.assertIn("screenshot", describe(Context(vision_ready=True)))

    def test_it_can_name_the_platform(self):
        self.assertIn("Windows", describe(Context(), platform_name="Windows"))


class CandidateTests(unittest.TestCase):
    def test_adapters_without_capabilities_are_dropped(self):
        class Dead:
            def capabilities(self):
                return set()

        class Alive:
            def capabilities(self):
                return {"uia"}

        self.assertEqual([type(a).__name__ for a in candidates([Dead(), None, Alive()])],
                         ["Alive"])

    def test_a_broken_capability_probe_drops_the_adapter(self):
        class Broken:
            def capabilities(self):
                raise RuntimeError("no")

        self.assertEqual(candidates([Broken()]), [])


if __name__ == "__main__":
    unittest.main()
