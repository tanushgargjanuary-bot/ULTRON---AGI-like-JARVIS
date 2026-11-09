"""Regression tests for fractional bandit evidence and decayed strategy replay."""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.bandit import Thompson, UCB1
from custom_jarvis.metacog import HALF_LIFE_DAYS, Ledger


class WeightedBandits(unittest.TestCase):
    def test_ucb1_weights_scale_pulls_and_reward(self):
        bandit = UCB1(["strategy"], c=0.0)
        bandit.update("strategy", 1.0, weight=0.25)
        bandit.update("strategy", 0.0, weight=0.75)

        stats = bandit.stats()["strategy"]
        self.assertAlmostEqual(stats["pulls"], 1.0)
        self.assertAlmostEqual(stats["mean"], 0.25)

    def test_subunit_total_weight_keeps_ucb_scores_finite(self):
        bandit = UCB1(["stale", "new"])
        bandit.update("stale", 1.0, weight=0.25)

        scores = bandit.scores()
        self.assertEqual(scores[0][0], "new")
        self.assertTrue(all(math.isfinite(score) or score == math.inf
                            for _name, score in scores))
        self.assertEqual(bandit.choose(), "new")

    def test_zero_and_negative_weights_do_not_create_evidence(self):
        bandit = UCB1(["strategy"])
        bandit.update("strategy", 1.0, weight=0.0)
        bandit.update("strategy", 0.0, weight=-2.0)

        stats = bandit.stats()["strategy"]
        self.assertEqual(stats["pulls"], 0)
        self.assertEqual(stats["mean"], 0.0)
        self.assertEqual(bandit.choose(), "strategy")

    def test_non_finite_weights_are_rejected(self):
        bandit = UCB1(["strategy"])
        for weight in (math.nan, math.inf, -math.inf):
            with self.subTest(weight=weight):
                with self.assertRaises(ValueError):
                    bandit.update("strategy", 1.0, weight=weight)

    def test_thompson_sampling_weights_posterior_and_pull_count(self):
        bandit = Thompson(["strategy"], prior=(1.0, 1.0))
        bandit.update("strategy", 1.0, weight=0.25)
        bandit.update("strategy", 0.0, weight=0.75)

        alpha, beta = bandit.posterior("strategy")
        stats = bandit.stats()["strategy"]
        self.assertAlmostEqual(alpha, 1.25)
        self.assertAlmostEqual(beta, 1.75)
        self.assertAlmostEqual(stats["pulls"], 1.0)
        self.assertAlmostEqual(stats["mean"], 0.25)

    def test_metacognition_replay_passes_decay_as_sample_weight(self):
        class RecordingBandit:
            instance = None

            def __init__(self, names):
                self.names = list(names)
                self.updates = []
                RecordingBandit.instance = self

            def update(self, name, reward, weight=1.0):
                self.updates.append((name, reward, weight))

            def choose(self):
                return self.names[0]

            def scores(self):
                return [(name, 0.5) for name in self.names]

        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / "metacog.json")
            ledger.record_attempt("debugging", "read_trace", True)
            ledger.record_attempt("debugging", "read_trace", False)

            now = 1_800_000_000.0
            history = ledger._data["strategies"]["debugging"]["read_trace"]["recent"]
            history[0]["at"] = now - HALF_LIFE_DAYS * 86400.0
            history[1]["at"] = now

            with (
                patch("custom_jarvis.metacog.UCB1", RecordingBandit),
                patch("custom_jarvis.metacog.time.time", return_value=now),
            ):
                ledger.choose_strategy("debugging", ["read_trace"])

        updates = RecordingBandit.instance.updates
        self.assertEqual(len(updates), 2)
        self.assertEqual(updates[0][0:2], ("read_trace", 1.0))
        self.assertAlmostEqual(updates[0][2], 0.5)
        self.assertEqual(updates[1][0:2], ("read_trace", 0.0))
        self.assertAlmostEqual(updates[1][2], 1.0)


if __name__ == "__main__":
    unittest.main()
