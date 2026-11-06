"""tests/test_reputation.py — does the trust number mean what it claims?

    The claims being tested are the ones a user would notice:
      - an unproven tool does not outrank a proven one;
      - a long perfect record outranks a short perfect record;
      - a bad last week outweighs a good last month (decay);
      - with no evidence at all, nothing is preferred.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.reputation import Record, Reputation


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class EvidenceTests(unittest.TestCase):
    def test_a_fresh_record_knows_nothing(self):
        record = Record("tool")
        self.assertEqual(record.samples, 0)
        self.assertAlmostEqual(record.mean, 0.5)
        self.assertGreater(record.lower(), 0.0)
        self.assertLess(record.lower(), 0.2)

    def test_successes_raise_the_bound_and_failures_lower_it(self):
        good, bad = Reputation(), Reputation()
        for _ in range(9):
            good.record("t", True)
            bad.record("t", False)
        self.assertGreater(good.lower("t"), 0.6)
        self.assertLess(bad.lower("t"), 0.2)

    def test_four_out_of_four_is_not_certainty(self):
        rep = Reputation()
        for _ in range(4):
            rep.record("t", True)
        self.assertLess(rep.lower("t"), 0.6)
        self.assertGreater(rep.get("t").mean, 0.8)

    def test_weighted_evidence(self):
        rep = Reputation()
        rep.record("t", True, weight=5.0)
        self.assertAlmostEqual(rep.get("t").alpha, 6.0)
        rep.record("t", False, weight=0.5)
        self.assertAlmostEqual(rep.get("t").beta, 1.5)

    def test_zero_weight_records_nothing_useful_but_counts_a_sample(self):
        rep = Reputation()
        rep.record("t", True, weight=0.0)
        self.assertEqual(rep.get("t").samples, 1)
        self.assertAlmostEqual(rep.get("t").evidence, 0.0)


class RankingTests(unittest.TestCase):
    def test_proven_beats_unproven(self):
        rep = Reputation()
        for _ in range(trials := 20):
            rep.record("reliable", True)
        rep.record("newcomer", True)
        self.assertEqual(rep.ranked_tools(["reliable", "newcomer"])[0], "reliable")
        self.assertGreater(trials, 0)

    def test_unproven_tools_answer_none_at_a_minimum(self):
        rep = Reputation()
        rep.record("a", True)                       # 1/1, lower bound ~0.1
        self.assertIsNone(rep.best(["a"], minimum=0.5))
        for _ in range(19):
            rep.record("a", True)
        self.assertEqual(rep.best(["a"], minimum=0.5), "a")

    def test_a_flaky_tool_loses_to_a_steady_one(self):
        rep = Reputation()
        for ok in (True, False, True, False, True, False, True, False):
            rep.record("flaky", ok)
        for _ in range(8):
            rep.record("steady", True)
        self.assertEqual(rep.ranked_tools(["flaky", "steady"])[0], "steady")

    def test_ranking_is_complete_and_deterministic(self):
        rep = Reputation()
        names = ["b", "a", "c"]
        self.assertEqual(sorted(rep.ranked_tools(names)), sorted(names))
        self.assertEqual(rep.ranked_tools(names), rep.ranked_tools(names))

    def test_empty_input_ranks_to_nothing(self):
        self.assertEqual(Reputation().rank([]), [])
        self.assertIsNone(Reputation().best([]))


class DecayTests(unittest.TestCase):
    def test_evidence_fades_but_the_prior_remains(self):
        clock = Clock()
        rep = Reputation(half_life=24 * 3600, clock=clock)
        for _ in range(20):
            rep.record("t", True)
        fresh = rep.lower("t")
        clock.advance(24 * 3600)                     # one half-life
        aged = rep.lower("t")
        self.assertLess(aged, fresh)
        self.assertGreater(aged, 0.0)

    def test_a_bad_week_beats_a_good_month(self):
        clock = Clock()
        rep = Reputation(half_life=7 * 24 * 3600, clock=clock)
        for _ in range(20):
            rep.record("t", True)                    # a good month
        clock.advance(30 * 24 * 3600)
        for _ in range(6):
            rep.record("t", False)                   # then a bad week
        self.assertLess(rep.get("t").mean, 0.55)

    def test_decay_never_produces_invalid_parameters(self):
        clock = Clock()
        rep = Reputation(half_life=60, clock=clock)
        rep.record("t", True)
        clock.advance(10 ** 7)
        record = rep.get("t")
        self.assertGreater(record.alpha, 0.0)
        self.assertGreater(record.beta, 0.0)
        self.assertTrue(0.0 < record.lower() < 1.0)


class StateTests(unittest.TestCase):
    def test_snapshot_restore_round_trip(self):
        rep = Reputation()
        for ok in (True, True, False, True):
            rep.record("tool_a", ok)
        snapshot = rep.snapshot()

        clone = Reputation()
        clone.restore(snapshot)
        self.assertAlmostEqual(clone.lower("tool_a"), rep.lower("tool_a"), places=9)
        self.assertEqual(clone.get("tool_a").samples, 4)

    def test_restore_tolerates_junk(self):
        rep = Reputation()
        rep.restore({})
        rep.restore({"records": {"x": "not a dict"}})
        rep.restore(None)                                    # type: ignore[arg-type]
        self.assertEqual(rep.get("x").samples, 0)

    def test_reset_clears_everything(self):
        rep = Reputation()
        rep.record("a", True)
        rep.reset()
        self.assertEqual(rep.get("a").samples, 0)

    def test_snapshot_is_serialisable(self):
        import json

        rep = Reputation()
        rep.record("a", True)
        json.dumps(rep.snapshot())          # must not raise


if __name__ == "__main__":
    unittest.main()
