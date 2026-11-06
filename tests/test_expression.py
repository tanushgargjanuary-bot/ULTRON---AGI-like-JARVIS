"""Offline tests for facial expression (core/expression.py + core/avatar.py).

The avatar can already lip-sync. These cover the added channel — named
expressions driven by meaning — and, most importantly, the guard that keeps a
smile off a sentence that reports a failure.
"""

import unittest

from core import expression as ex
from core.expression import Expression


class ExpressionMathTests(unittest.TestCase):
    def test_values_are_clamped(self):
        wild = Expression(smile=9.0, brow_raise=-9.0, squint=5.0).clamped()
        self.assertEqual(wild.smile, 1.0)
        self.assertEqual(wild.brow_raise, -1.0)
        self.assertEqual(wild.squint, 1.0)

    def test_nan_and_junk_become_zero(self):
        junk = Expression(smile=float("nan"), brow_raise="nonsense").clamped()
        self.assertEqual(junk.smile, 0.0)
        self.assertEqual(junk.brow_raise, 0.0)

    def test_the_renderer_ceiling_is_lower_than_the_maths_ceiling(self):
        capped = Expression(smile=1.0, squint=1.0).capped()
        self.assertLessEqual(capped.smile, ex.MAX.smile)
        self.assertLessEqual(capped.squint, ex.MAX.squint)

    def test_blend_moves_between_the_two(self):
        start = Expression(smile=0.0)
        end = Expression(smile=0.5)
        self.assertAlmostEqual(start.blend(end, 0.0).smile, 0.0)
        self.assertAlmostEqual(start.blend(end, 1.0).smile, 0.5)
        self.assertAlmostEqual(start.blend(end, 0.5).smile, 0.25)

    def test_blend_rejects_out_of_range_t(self):
        self.assertAlmostEqual(Expression().blend(Expression(smile=0.5), 5.0).smile, 0.5)
        self.assertAlmostEqual(Expression().blend(Expression(smile=0.5), -5.0).smile, 0.0)

    def test_scaled_keeps_the_ceiling(self):
        self.assertAlmostEqual(Expression(smile=0.4).scaled(0.5).smile, 0.2)
        self.assertLessEqual(Expression(smile=1.0).scaled(10.0).smile, ex.MAX.smile)

    def test_neutral_detection(self):
        self.assertTrue(ex.NEUTRAL.is_neutral())
        self.assertFalse(Expression(smile=0.1).is_neutral())

    def test_tuple_and_dict_agree(self):
        value = Expression(smile=0.2, asym=0.1)
        self.assertEqual(len(value.as_tuple()), 7)
        self.assertAlmostEqual(value.as_dict()["smile"], value.as_tuple()[0])


class TagTests(unittest.TestCase):
    def test_known_tags(self):
        self.assertGreater(ex.from_tag("amused").smile, 0)
        self.assertGreater(ex.from_tag("concerned").brow_furrow, 0)
        self.assertGreater(ex.from_tag("concentrating").brow_furrow, 0)
        self.assertGreater(ex.from_tag("surprised").lid_widen, 0)

    def test_aliases(self):
        self.assertEqual(ex.from_tag("happy"), ex.from_tag("pleased"))
        self.assertEqual(ex.from_tag("worried"), ex.from_tag("concerned"))

    def test_qualifiers_do_not_break_it(self):
        self.assertGreater(ex.from_tag("slightly amused").smile, 0)

    def test_case_and_punctuation(self):
        self.assertGreater(ex.from_tag("  Amused!  ").smile, 0)

    def test_unknown_tags_are_neutral_rather_than_random(self):
        self.assertTrue(ex.from_tag("garrulous").is_neutral())
        self.assertTrue(ex.from_tag("").is_neutral())
        self.assertTrue(ex.from_tag(None).is_neutral())

    def test_every_tag_is_bounded(self):
        for name in ex.TAGS:
            expression = ex.from_tag(name)
            self.assertLessEqual(abs(expression.smile), ex.MAX.smile, name)
            self.assertGreaterEqual(expression.smile, -ex.MAX.smile, name)


class GuardTests(unittest.TestCase):
    def test_a_smile_is_removed_from_a_failure_report(self):
        guarded = ex.guard(ex.from_tag("pleased"), "I could not open that, sorry.")
        self.assertLessEqual(guarded.smile, 0.0)

    def test_concern_survives_bad_news(self):
        guarded = ex.guard(ex.from_tag("concerned"), "That failed.")
        self.assertGreater(guarded.brow_furrow, 0)

    def test_a_normal_sentence_keeps_its_expression(self):
        self.assertAlmostEqual(
            ex.guard(ex.from_tag("pleased"), "Here is your schedule.").smile,
            ex.from_tag("pleased").smile,
        )

    def test_problem_detection(self):
        for text in ("Error: no device", "I can't reach it", "permission denied",
                     "nothing was found"):
            self.assertTrue(ex.looks_like_problem(text), text)
        self.assertFalse(ex.looks_like_problem("All three reminders are set."))


class ProsodyAndStateTests(unittest.TestCase):
    def test_prosody_is_bounded(self):
        for level, variance in ((0, 0), (1, 1), (5, -3), (0.4, 0.9)):
            expression = ex.from_prosody(level, variance)
            self.assertLessEqual(abs(expression.brow_raise), ex.MAX.brow_raise)
            self.assertGreaterEqual(expression.squint, 0.0)

    def test_emphasis_lifts_the_brows_more_than_quiet_speech(self):
        self.assertGreater(ex.from_prosody(0.9, 0.5).brow_raise,
                           ex.from_prosody(0.1, 0.0).brow_raise)

    def test_states_have_a_resting_face(self):
        self.assertGreater(ex.from_state("THINKING").brow_furrow, 0)
        self.assertGreater(ex.from_state("LISTENING").brow_raise, 0)
        self.assertTrue(ex.from_state("SLEEPING").is_neutral())

    def test_with_tag_mixes_state_and_tag(self):
        mixed = ex.with_tag(ex.from_state("LISTENING"), "amused", 0.65, "")
        self.assertGreater(mixed.smile, 0)
        self.assertGreater(mixed.brow_raise, 0)

    def test_with_tag_respects_the_guard(self):
        mixed = ex.with_tag(ex.NEUTRAL, "pleased", 0.65, "I could not do that.")
        self.assertLessEqual(mixed.smile, 0.0)

    def test_combine_sums_and_caps(self):
        total = ex.combine((Expression(smile=0.4), 1.0), (Expression(smile=0.4), 1.0))
        self.assertLessEqual(total.smile, ex.MAX.smile)


class AvatarIntegrationTests(unittest.TestCase):
    """The renderer must actually move, and settle back."""

    @classmethod
    def setUpClass(cls):
        from core.avatar import HoloAvatar

        cls.avatar_class = HoloAvatar
        cls.shared = HoloAvatar()      # building the mesh once keeps this fast

    def fresh(self):
        import copy

        return copy.deepcopy(self.shared)

    def test_a_smile_reaches_the_paint_state(self):
        avatar = self.fresh()
        for _ in range(40):
            avatar.step(0.02, 0.0, speaking=False, state="LISTENING",
                        expr=ex.from_tag("pleased"))
        self.assertGreater(avatar._smile, 0.05)
        self.assertGreater(avatar._ex.smile, 0.05)

    def test_concern_furrows_the_brow(self):
        avatar = self.fresh()
        avatar.step(0.02, 0.0, expr=ex.NEUTRAL)
        rest = avatar._brow_bias
        for _ in range(40):
            avatar.step(0.02, 0.0, expr=ex.from_tag("concentrating"))
        self.assertLess(avatar._brow_bias, rest)

    def test_surprise_opens_the_lids(self):
        avatar = self.fresh()
        for _ in range(40):
            avatar.step(0.02, 0.0, state="LISTENING", expr=ex.from_tag("surprised"))
        self.assertGreater(avatar._lids, 0.9)

    def test_it_returns_to_neutral_when_the_tag_is_dropped(self):
        avatar = self.fresh()
        for _ in range(60):
            avatar.step(0.02, 0.0, expr=ex.from_tag("pleased"))
        self.assertGreater(avatar._smile, 0.05)
        for _ in range(200):
            avatar.step(0.02, 0.0, expr=None)
        self.assertLess(abs(avatar._smile), 0.02)

    def test_no_expression_keeps_the_old_behaviour(self):
        avatar = self.fresh()
        for _ in range(30):
            avatar.step(0.02, 0.3, speaking=False, state="IDLE")
        self.assertLess(abs(avatar._smile), 0.001)
        self.assertLess(abs(avatar._squint), 0.001)

    def test_the_animation_does_not_depend_on_the_frame_rate(self):
        slow, fast = self.fresh(), self.fresh()
        for _ in range(10):                     # 10 frames of 100 ms
            slow.step(0.1, 0.0, expr=ex.from_tag("pleased"))
        for _ in range(50):                     # 50 frames of 20 ms
            fast.step(0.02, 0.0, expr=ex.from_tag("pleased"))
        self.assertAlmostEqual(slow._smile, fast._smile, delta=0.05)

    def test_junk_input_cannot_break_the_render_loop(self):
        avatar = self.fresh()
        for junk in ("amused", 42, object(), Expression(smile=float("inf"))):
            avatar.step(0.02, 0.0, expr=junk)
        self.assertLessEqual(abs(avatar._smile), ex.MAX.smile)

    def test_speech_still_closes_the_mouth_with_an_expression_on(self):
        avatar = self.fresh()
        for _ in range(30):
            avatar.step(0.02, 0.0, speaking=True, expr=ex.from_tag("amused"))
        for _ in range(60):
            avatar.step(0.02, 0.0, speaking=False, expr=ex.from_tag("amused"))
        self.assertLess(avatar._mouth, 0.12)


if __name__ == "__main__":
    unittest.main()
