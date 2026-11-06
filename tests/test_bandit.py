"""tests/test_bandit.py — does the learner actually learn?

    The tests that matter are simulations. A bandit that "looks right" can still
    fail to concentrate on the good arm, and the only way to know is to run it
    against a known-reward environment and measure.

    Determinism: every probabilistic test seeds its RNG, so a failure is a
    failure and not a bad afternoon.
"""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.bandit import UCB1, Contextual, Thompson


def play(bandit, truths, rng, rounds=400, blocked=()):
    """Simulate `rounds` interactions with known success probabilities."""
    for _ in range(rounds):
        arm = bandit.choose(blocked)
        reward = 1.0 if rng.random() < truths[arm] else 0.0
        bandit.update(arm, reward)


class UCB1Tests(unittest.TestCase):
    def test_every_arm_is_tried_once_first(self):
        # Choose-then-update, because an arm that never gets feedback correctly
        # keeps being chosen: the learner cannot learn about it otherwise.
        band = UCB1(["a", "b", "c"])
        first = []
        for _ in range(3):
            arm = band.choose()
            first.append(arm)
            band.update(arm, 0.5)
        self.assertEqual(sorted(first), ["a", "b", "c"])

    def test_it_concentrates_on_the_best_arm(self):
        rng = random.Random(11)
        truths = {"good": 0.9, "ok": 0.5, "bad": 0.1}
        band = UCB1(truths)
        play(band, truths, rng, rounds=600)
        stats = band.stats()
        self.assertGreater(stats["good"]["pulls"], stats["bad"]["pulls"] * 3)

    def test_a_blocked_arm_is_never_chosen(self):
        truths = {"a": 0.9, "b": 0.1}
        band = UCB1(truths)
        for _ in range(200):
            arm = band.choose(blocked={"b"})
            self.assertEqual(arm, "a")
            band.update(arm, 1.0)

    def test_all_blocked_returns_none(self):
        band = UCB1(["a", "b"])
        self.assertIsNone(band.choose(blocked={"a", "b"}))

    def test_scores_put_untried_arms_first(self):
        band = UCB1(["a", "b"])
        band.update("a", 1.0)
        scores = dict(band.scores())
        self.assertEqual(scores["b"], float("inf"))
        self.assertGreater(scores["a"], 0.0)

    def test_rewards_are_clamped(self):
        band = UCB1(["a"])
        band.update("a", 99.0)
        self.assertEqual(band.stats()["a"]["mean"], 1.0)
        band.update("a", -5.0)
        self.assertLessEqual(band.stats()["a"]["mean"], 1.0)


class ThompsonTests(unittest.TestCase):
    def test_untried_arms_first(self):
        band = Thompson(["a", "b"], rng=random.Random(1))
        seen = set()
        for _ in range(4):
            arm = band.choose()
            seen.add(arm)
            band.update(arm, 0.5)
        self.assertEqual(seen, {"a", "b"})

    def test_it_concentrates_on_the_best_arm(self):
        rng = random.Random(2026)
        truths = {"good": 0.85, "ok": 0.5, "bad": 0.15}
        band = Thompson(truths, rng=rng)
        play(band, truths, rng, rounds=600)
        stats = band.stats()
        self.assertGreater(stats["good"]["pulls"], stats["bad"]["pulls"] * 3)
        self.assertGreater(stats["good"]["mean"], 0.7)

    def test_posterior_moves_in_the_right_direction(self):
        band = Thompson(["a"], rng=random.Random(3))
        band.update("a", 0.0)
        alpha_zero, beta_zero = band.posterior("a")
        self.assertEqual(beta_zero, 2.0)
        band.update("a", 1.0)
        alpha_one, _ = band.posterior("a")
        self.assertGreater(alpha_one, alpha_zero)

    def test_asymmetric_prior_is_respected(self):
        # A provider believed fast-but-flaky starts from that belief.
        band = Thompson(["a", "b"], prior=(1.0, 4.0), rng=random.Random(9))
        for _ in range(2):
            band.choose()
        alpha, beta = band.posterior("a")
        self.assertLess(alpha / (alpha + beta), 0.5)

    def test_blocked_arms_are_excluded(self):
        band = Thompson(["a", "b"], rng=random.Random(4))
        for _ in range(20):
            arm = band.choose(blocked={"b"})
            self.assertEqual(arm, "a")
            band.update(arm, 0.5)

    def test_determinism_with_the_same_seed(self):
        def run():
            rng = random.Random(77)
            band = Thompson(["a", "b", "c"], rng=rng)
            truths = {"a": 0.6, "b": 0.4, "c": 0.5}
            play(band, truths, rng, rounds=100)
            return band.stats()

        self.assertEqual(run(), run())


class ContextualTests(unittest.TestCase):
    def test_contexts_learn_separately(self):
        rng = random.Random(13)
        band = Contextual(lambda arms: Thompson(arms, rng=rng))
        # A is better for "chat", B is better for "code".
        truths = {"chat": {"A": 0.9, "B": 0.1}, "code": {"A": 0.1, "B": 0.9}}
        for _ in range(400):
            for context, table in truths.items():
                arm = band.choose(context, arms=list(table))
                reward = 1.0 if rng.random() < table[arm] else 0.0
                band.update(context, arm, reward)

        stats = band.stats()
        self.assertGreater(stats["chat"]["A"]["pulls"], stats["chat"]["B"]["pulls"])
        self.assertGreater(stats["code"]["B"]["pulls"], stats["code"]["A"]["pulls"])

    def test_new_arms_can_join_a_live_context(self):
        band = Contextual(lambda arms: Thompson(arms, rng=random.Random(2)))
        band.choose("chat", arms=["A"])
        band.bandit("chat", arms=["B"])
        self.assertEqual(sorted(band.bandit("chat").names()), ["A", "B"])


class BookkeepingTests(unittest.TestCase):
    def test_add_and_forget(self):
        band = Thompson(["a"])
        band.add_arm("b")
        self.assertEqual(sorted(band.names()), ["a", "b"])
        band.forget("b")
        self.assertEqual(band.names(), ["a"])

    def test_updating_an_unknown_arm_creates_it_rather_than_crashing(self):
        band = Thompson([])
        band.update("surprise", 1.0)
        self.assertEqual(band.stats()["surprise"]["pulls"], 1)

    def test_empty_bandit_chooses_nothing(self):
        self.assertIsNone(Thompson([]).choose())
        self.assertIsNone(UCB1([]).choose())

    def test_len(self):
        self.assertEqual(len(UCB1(["a", "b"])), 2)


if __name__ == "__main__":
    unittest.main()
