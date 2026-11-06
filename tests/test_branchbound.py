"""tests/test_branchbound.py — when to act, when to ask, and why the two differ.

THE BEHAVIOUR THESE TESTS PIN DOWN
    1. A clear winner acts.
    2. A weak best candidate asks, even if it is the best one available.
    3. A strong-but-contested best candidate asks, because 0.71 against 0.70 is
       a coin flip wearing a percentage.
    4. Pruning actually prunes — the count is asserted, so a future change that
       quietly turns branch-and-bound into exhaustive search is visible.
    5. Asking is never a crash: an empty candidate list is a question, not an
       exception.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.branchbound import Candidate, decide


class DecisionTests(unittest.TestCase):
    def test_clear_winner_acts(self):
        result = decide([Candidate("WhatsApp", 0.93), Candidate("Telegram", 0.41)])
        self.assertFalse(result.ask)
        self.assertEqual(result.chosen.label, "WhatsApp")
        # A rival that cannot reach the threshold is pruned before it can be a
        # "runner-up": 0.41 is not a serious alternative to 0.93, and reporting
        # it as one would make every decision look contested.
        self.assertIsNone(result.runner_up)
        self.assertAlmostEqual(result.margin, 0.93, places=6)

    def test_nothing_clears_the_threshold_asks(self):
        result = decide([Candidate("WhatsApp", 0.62), Candidate("Telegram", 0.30)])
        self.assertTrue(result.ask)
        self.assertIsNone(result.chosen)
        self.assertIn("threshold", result.reason)

    def test_a_narrow_lead_asks_even_above_the_threshold(self):
        result = decide([Candidate("Chrome", 0.74), Candidate("Chrome Remote Desktop", 0.71)])
        self.assertTrue(result.ask)
        self.assertIn("close", result.reason)
        self.assertEqual(result.question(), "Did you mean Chrome, or Chrome Remote Desktop?")

    def test_the_question_is_empty_when_not_asking(self):
        result = decide([Candidate("Notepad", 0.99)])
        self.assertEqual(result.question(), "")

    def test_no_candidates_is_a_question_not_a_crash(self):
        result = decide([])
        self.assertTrue(result.ask)
        self.assertIsNone(result.chosen)
        self.assertEqual(result.question(), "")

    def test_a_single_strong_candidate_acts_without_a_runner_up(self):
        result = decide([Candidate("Calculator", 0.95)])
        self.assertFalse(result.ask)
        self.assertIsNone(result.runner_up)
        self.assertEqual(result.margin, 0.95)


class PruningTests(unittest.TestCase):
    def _tree(self):
        # "chrome" -> {Chrome 0.88, Chrome Remote Desktop 0.31}
        # "chromium" -> 0.22, "chromecast" -> 0.12
        children = [Candidate("Chrome", 0.88), Candidate("Chrome Remote Desktop", 0.31)]
        return [
            Candidate("chrome", 0.88, children=children),
            Candidate("chromium", 0.22),
            Candidate("chromecast", 0.12),
        ]

    def test_hopeless_branches_are_pruned(self):
        result = decide(self._tree(), threshold=0.70)
        # chromium and chromecast cannot reach 0.70 and are never expanded.
        self.assertGreaterEqual(result.pruned, 2)
        self.assertFalse(result.ask)

    def test_a_tighter_bound_prunes_more(self):
        loose = decide(self._tree(), threshold=0.70)
        tight = decide(
            self._tree(),
            threshold=0.70,
            optimism=lambda node: node.score,      # no credit for children
        )
        self.assertGreaterEqual(tight.pruned, loose.pruned)

    def test_children_are_reachable_when_the_parent_is_weak(self):
        parent = Candidate("chrome", 0.40, children=[Candidate("Chrome", 0.91)])
        result = decide([parent])
        self.assertFalse(result.ask)
        self.assertEqual(result.chosen.label, "Chrome")

    def test_search_is_bounded(self):
        """A pathological expander must not hang the keystroke path."""
        wide = [
            Candidate(f"c{i}", 0.75, children=[Candidate(f"c{i}.{j}", 0.76) for j in range(50)])
            for i in range(50)
        ]
        result = decide(wide, max_nodes=25)
        self.assertLessEqual(result.explored, 25)
        self.assertTrue(result.ask or result.chosen is not None)

    def test_explored_counts_are_reported(self):
        # 3 roots + the 2 children of the only branch that survived its bound.
        result = decide(self._tree())
        self.assertEqual(result.explored, 5)
        self.assertEqual(result.pruned, 3)          # chromium, chromecast, CRD
        self.assertFalse(result.ask)


class ThresholdDisciplineTests(unittest.TestCase):
    def test_matching_the_specified_one_rule(self):
        """The 0.70 lower bound is the project's rule; this verifies the module
        implements exactly it rather than a nearby number."""
        self.assertTrue(decide([Candidate("x", 0.699)], threshold=0.70).ask)
        self.assertFalse(decide([Candidate("x", 0.701)], threshold=0.70).ask)

    def test_scores_are_clamped_into_range(self):
        self.assertEqual(Candidate("x", 5.0).score, 1.0)
        self.assertEqual(Candidate("x", -3.0).score, 0.0)

    def test_payload_survives_the_decision(self):
        result = decide([Candidate("Notepad", 0.99, payload={"app": "notepad.exe"})])
        self.assertEqual(result.chosen.payload, {"app": "notepad.exe"})


if __name__ == "__main__":
    unittest.main()
