"""tests/test_selfimprove.py — does the improvement loop only keep real gains?

    The dangerous failure here is not a crash. It is a loop that accepts a change
    because it looked better once, which over a few hundred rounds walks the
    system into a configuration nobody chose. So most of these tests are about
    rejection: noise, small effects, safety regressions, tiny samples, and anything
    protected.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.selfimprove import (
    Artefact,
    Budget,
    Case,
    Lineage,
    compare,
    improve,
    sign_test_p,
    wilson_interval,
)


class Table:
    """An evaluator whose scores are a lookup table per value.

    Explicit numbers rather than a model of a task, so the tests are about the
    loop's arithmetic and not about whether a fake benchmark is realistic.
    """

    def __init__(self, cases, scores):
        self._cases = list(cases)
        self._scores = scores          # value -> {case_id: score}

    def cases(self):
        return list(self._cases)

    def score(self, value, case):
        return float(self._scores.get(value, {}).get(case.id, 0.0))


def cases(n=10, safety_at=()):
    return [Case(f"c{i}", safety=i in safety_at) for i in range(n)]


class SignTestTests(unittest.TestCase):
    def test_closed_forms(self):
        self.assertAlmostEqual(sign_test_p(8, 0), 0.0078, places=4)
        self.assertAlmostEqual(sign_test_p(6, 0), 0.0313, places=4)
        self.assertAlmostEqual(sign_test_p(5, 0), 0.0625, places=4)
        self.assertAlmostEqual(sign_test_p(4, 1), 0.375, places=4)

    def test_no_evidence_is_not_significant(self):
        self.assertEqual(sign_test_p(0, 0), 1.0)
        self.assertEqual(sign_test_p(5, 5), 1.0)

    def test_it_is_symmetric(self):
        self.assertAlmostEqual(sign_test_p(7, 1), sign_test_p(1, 7))

    def test_six_of_six_is_the_smallest_perfect_record_that_passes(self):
        self.assertLess(sign_test_p(6, 0), 0.05)
        self.assertGreater(sign_test_p(5, 0), 0.05)


class CompareTests(unittest.TestCase):
    def test_deltas_are_per_case_not_aggregate_luck(self):
        table = Table(cases(4), {
            "old": {"c0": 0.5, "c1": 0.5, "c2": 0.5, "c3": 0.5},
            "new": {"c0": 0.9, "c1": 0.9, "c2": 0.3, "c3": 0.3},
        })
        comparison = compare("old", "new", table)
        # The mean says +0.10 and the votes say 2-2. Both are true, and that is
        # the reason the gate needs the sign test as well as the effect size: a
        # candidate can win on average by winning big twice and losing small
        # twice, which is not a general improvement, it is two cases.
        self.assertEqual((comparison.wins, comparison.losses, comparison.ties), (2, 2, 0))
        self.assertAlmostEqual(comparison.delta, 0.1, places=6)
        self.assertEqual(comparison.p_value, 1.0)

    def test_ties_are_counted_not_ignored(self):
        table = Table(cases(4), {"old": {"c0": 1.0}, "new": {"c0": 1.0}})
        self.assertEqual(compare("old", "new", table).ties, 4)

    def test_safety_regressions_are_named(self):
        table = Table(cases(3, safety_at=(1,)), {
            "old": {"c0": 0.1, "c1": 0.9, "c2": 0.1},
            "new": {"c0": 0.9, "c1": 0.1, "c2": 0.9},
        })
        comparison = compare("old", "new", table)
        self.assertEqual(comparison.safety_regressions, ("c1",))

    def test_per_case_scores_are_kept_for_review(self):
        table = Table(cases(2), {"old": {"c0": 0.1}, "new": {"c0": 0.2}})
        self.assertIn("c0", compare("old", "new", table).per_case)


class ImproveTests(unittest.TestCase):
    def _all_better(self, n=8, delta=0.2):
        old = {f"c{i}": 0.5 for i in range(n)}
        new = {f"c{i}": 0.5 + delta for i in range(n)}
        return Table(cases(n), {"old": old, "new": new})

    def test_a_real_improvement_is_accepted(self):
        verdict = improve(Artefact("threshold", "old", space=("new",)), self._all_better())
        self.assertTrue(verdict.accepted)
        self.assertEqual(verdict.value, "new")
        self.assertIn("8/8", verdict.reason)

    def test_noise_is_rejected(self):
        table = Table(cases(8), {"old": {"c0": 0.5}, "new": {"c0": 0.9}})
        verdict = improve(Artefact("x", "old", space=("new",)), table)
        self.assertFalse(verdict.accepted)
        self.assertIn("better by enough", verdict.reason)

    def test_a_tiny_effect_is_rejected_even_when_unanimous(self):
        verdict = improve(
            Artefact("x", "old", space=("new",)), self._all_better(delta=0.005),
            min_effect=0.02,
        )
        self.assertFalse(verdict.accepted)

    def test_a_safety_regression_blocks_a_better_average(self):
        table = Table(cases(8, safety_at=(3,)), {
            "old": {f"c{i}": 0.5 for i in range(8)} | {"c3": 0.9},
            "new": {f"c{i}": 0.7 for i in range(8)} | {"c3": 0.1},
        })
        verdict = improve(Artefact("x", "old", space=("new",)), table)
        self.assertFalse(verdict.accepted)
        self.assertIn("better by enough", verdict.reason)

    def test_too_few_cases_is_refused_before_any_trial(self):
        table = Table(cases(3), {"old": {"c0": 0.1}, "new": {"c0": 0.9}})
        verdict = improve(Artefact("x", "old", space=("new",)), table)
        self.assertFalse(verdict.accepted)
        self.assertEqual(verdict.tried, 0)
        self.assertIn("3 cases", verdict.reason)

    def test_protected_artefacts_need_a_human(self):
        verdict = improve(
            Artefact("permission_threshold", "old", space=("new",), protected=True),
            self._all_better(),
        )
        self.assertFalse(verdict.accepted)
        self.assertTrue(verdict.needs_human)
        self.assertIn("human decides", verdict.reason)
        self.assertIsNotNone(verdict.comparison)

    def test_irreversible_artefacts_need_a_human(self):
        verdict = improve(
            Artefact("delete_policy", "old", space=("new",), reversible=False),
            self._all_better(),
        )
        self.assertTrue(verdict.needs_human)

    def test_apply_runs_only_on_acceptance(self):
        applied = []
        improve(Artefact("x", "old", space=("new",)), self._all_better(),
                apply=applied.append)
        self.assertEqual(applied, ["new"])

        applied.clear()
        improve(Artefact("x", "old", space=("new",)),
                self._all_better(delta=0.0001), min_effect=0.05, apply=applied.append)
        self.assertEqual(applied, [])

    def test_a_failing_apply_is_not_an_acceptance(self):
        def boom(value):
            raise RuntimeError("wiring refused")

        verdict = improve(Artefact("x", "old", space=("new",)), self._all_better(), apply=boom)
        self.assertFalse(verdict.accepted)
        self.assertIn("applying it failed", verdict.reason)

    def test_the_best_of_several_candidates_wins(self):
        old = {f"c{i}": 0.5 for i in range(8)}
        table = Table(cases(8), {
            "old": old,
            "ok": {f"c{i}": 0.6 for i in range(8)},
            "best": {f"c{i}": 0.9 for i in range(8)},
        })
        verdict = improve(Artefact("x", "old", space=("ok", "best")), table)
        self.assertEqual(verdict.value, "best")

    def test_an_empty_search_space_changes_nothing(self):
        verdict = improve(Artefact("x", "old", space=()), self._all_better())
        self.assertFalse(verdict.accepted)
        self.assertEqual(verdict.value, "old")

    def test_the_budget_caps_how_many_candidates_are_tried(self):
        old = {f"c{i}": 0.5 for i in range(8)}
        table = Table(cases(8), {"old": old, **{
            f"v{n}": {f"c{i}": 0.9 for i in range(8)} for n in range(10)}})
        verdict = improve(
            Artefact("x", "old", space=tuple(f"v{n}" for n in range(10))), table, budget=3
        )
        self.assertLessEqual(verdict.tried, 3)

    def test_the_search_is_deterministic_for_a_seed(self):
        table = Table(cases(8), {"old": {f"c{i}": 0.5 for i in range(8)},
                                 "a": {f"c{i}": 0.9 for i in range(8)},
                                 "b": {f"c{i}": 0.9 for i in range(8)}})
        artefact = Artefact("x", "old", space=("a", "b"))
        first = improve(artefact, table, seed=7)
        second = improve(artefact, table, seed=7)
        self.assertEqual(first.value, second.value)

    def test_a_verdict_can_be_read_aloud(self):
        accepted = improve(Artefact("x", "old", space=("new",)), self._all_better())
        self.assertIn("Kept it", accepted.spoken())
        noisy = improve(Artefact("x", "old", space=("new",)),
                        Table(cases(8), {"old": {}, "new": {}}))
        self.assertIn("Left it alone", noisy.spoken())


class LineageTests(unittest.TestCase):
    def setUp(self):
        table = Table(cases(8), {"old": {f"c{i}": 0.5 for i in range(8)},
                                 "new": {f"c{i}": 0.9 for i in range(8)}})
        self.comparison = compare("old", "new", table)
        self.lineage = Lineage(clock=lambda: 1234.0)

    def test_history_is_per_artefact(self):
        self.lineage.record("threshold", 0.7, 0.75, self.comparison)
        self.lineage.record("retries", 2, 3, self.comparison)
        self.assertEqual(len(self.lineage.history("threshold")), 1)

    def test_previous_gives_the_value_to_roll_back_to(self):
        self.lineage.record("threshold", 0.7, 0.75, self.comparison)
        self.lineage.record("threshold", 0.75, 0.8, self.comparison)
        self.assertEqual(self.lineage.previous("threshold"), 0.75)

    def test_an_unknown_artefact_has_no_previous(self):
        self.assertIsNone(self.lineage.previous("nothing"))

    def test_snapshot_restores(self):
        self.lineage.record("threshold", 0.7, 0.75, self.comparison)
        payload = json.loads(self.lineage.to_json())
        clone = Lineage()
        clone.restore(payload)
        self.assertEqual(clone.previous("threshold"), 0.7)
        self.assertEqual(clone.entries[0].delta, self.comparison.delta)

    def test_restore_tolerates_junk(self):
        clone = Lineage()
        clone.restore({})
        clone.restore({"entries": [{"nonsense": True}]})
        clone.restore(None)
        self.assertEqual(clone.entries, [])


class BudgetTests(unittest.TestCase):
    def test_it_stops_when_spent(self):
        budget = Budget(max_experiments=2, clock=lambda: 0.0)
        self.assertTrue(budget.spend())
        self.assertTrue(budget.spend())
        self.assertFalse(budget.spend())
        self.assertIn("experiment", budget.reason())

    def test_it_stops_on_time_even_with_experiments_left(self):
        now = [0.0]
        budget = Budget(max_experiments=10, max_seconds=5.0, clock=lambda: now[0])
        now[0] = 6.0
        self.assertTrue(budget.stopped())
        self.assertIn("time", budget.reason())

    def test_a_zero_budget_does_nothing(self):
        self.assertTrue(Budget(max_experiments=0).stopped())


class ReportingTests(unittest.TestCase):
    def test_the_interval_brackets_the_estimate(self):
        low, high = wilson_interval(8, 10)
        self.assertLess(low, 0.8)
        self.assertGreater(high, 0.8)

    def test_no_trials_is_the_whole_range(self):
        self.assertEqual(wilson_interval(0, 0), (0.0, 1.0))

    def test_a_perfect_record_still_has_a_lower_bound_below_one(self):
        low, high = wilson_interval(10, 10)
        self.assertLess(low, 1.0)
        self.assertEqual(high, 1.0)


if __name__ == "__main__":
    unittest.main()
