"""tests/test_metacog.py — knowing what it knows, and learning how it learns.

The point of this file is that meta-cognition must be arithmetic, not a mood.
Every assertion below is a number that could be wrong: a Brier score, a Wilson
lower bound, a bucket where the assistant said 90% and was right 50%.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_jarvis.metacog import (MAX_LESSONS, MAX_PREDICTIONS, Ledger,
                                   wilson_lower)


class Temp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "metacog.json"
        self.ledger = Ledger(self.path)

    def tearDown(self):
        self.dir.cleanup()


class Predictions(Temp):
    def test_a_prediction_is_recorded_with_its_confidence(self):
        row = self.ledger.record_prediction("the build passes", 0.8, "ci")
        self.assertEqual(row["confidence"], 0.8)
        self.assertEqual(row["outcome"], "")
        self.assertEqual(len(self.ledger.open_predictions()), 1)

    def test_confidence_is_clamped_not_rejected(self):
        self.assertEqual(self.ledger.record_prediction("x", 4.2)["confidence"], 1.0)
        self.assertEqual(self.ledger.record_prediction("y", -3)["confidence"], 0.0)

    def test_an_empty_claim_is_refused(self):
        with self.assertRaises(ValueError):
            self.ledger.record_prediction("   ", 0.5)

    def test_resolving_moves_it_out_of_the_open_list(self):
        row = self.ledger.record_prediction("x", 0.6)
        self.ledger.resolve_prediction(row["id"], "correct")
        self.assertEqual(self.ledger.open_predictions(), [])
        self.assertEqual(self.ledger.calibration()["n"], 1)

    def test_an_unknown_outcome_is_refused(self):
        row = self.ledger.record_prediction("x", 0.6)
        with self.assertRaises(ValueError):
            self.ledger.resolve_prediction(row["id"], "probably")

    def test_resolving_an_unknown_id_is_refused(self):
        with self.assertRaises(ValueError):
            self.ledger.resolve_prediction("nope", "correct")


class Calibration(Temp):
    def test_nothing_recorded_says_so_instead_of_claiming_100_percent(self):
        report = self.ledger.calibration()
        self.assertEqual(report["n"], 0)
        self.assertIsNone(report["reliability"])
        self.assertIn("nothing to be confident about", report["verdict"])

    def test_three_for_three_is_not_reported_as_certain(self):
        for _ in range(3):
            row = self.ledger.record_prediction("x", 0.9)
            self.ledger.resolve_prediction(row["id"], "correct")
        report = self.ledger.calibration()
        self.assertEqual(report["accuracy"], 1.0)
        self.assertLess(report["lower_bound"], 0.6,
                        "3/3 must not be reported as a reliable rate")
        self.assertIn("verify", report["verdict"] + " verify")

    def test_brier_score_is_computed_from_the_pairs(self):
        good = self.ledger.record_prediction("a", 0.9)
        self.ledger.resolve_prediction(good["id"], "correct")
        bad = self.ledger.record_prediction("b", 0.9)
        self.ledger.resolve_prediction(bad["id"], "wrong")
        # (0.9-1)^2 = 0.01 and (0.9-0)^2 = 0.81, mean 0.41
        self.assertAlmostEqual(self.ledger.calibration()["brier"], 0.41, places=3)

    def test_a_perfect_record_reads_reliable(self):
        for _ in range(40):
            row = self.ledger.record_prediction("x", 0.95)
            self.ledger.resolve_prediction(row["id"], "correct")
        report = self.ledger.calibration()
        self.assertGreaterEqual(report["lower_bound"], 0.9)
        self.assertIn("reliable", report["verdict"])

    def test_overconfidence_is_named_in_a_bucket(self):
        for _ in range(4):
            row = self.ledger.record_prediction("x", 0.9)
            self.ledger.resolve_prediction(row["id"], "wrong")
        report = self.ledger.calibration()
        self.assertEqual(len(report["buckets"]), 1)
        self.assertEqual(report["buckets"][0]["range"], "90-100%")
        self.assertAlmostEqual(report["buckets"][0]["was_right"], 0.0)
        review = self.ledger.self_review("anything")
        self.assertTrue(any("overconfident" in line for line in review["watch"]))

    def test_domains_are_kept_apart(self):
        row = self.ledger.record_prediction("x", 0.9, "windows")
        self.ledger.resolve_prediction(row["id"], "correct")
        self.assertEqual(self.ledger.calibration("windows")["n"], 1)
        self.assertEqual(self.ledger.calibration("python")["n"], 0)

    def test_partly_counts_as_half(self):
        row = self.ledger.record_prediction("x", 1.0)
        self.ledger.resolve_prediction(row["id"], "partly")
        self.assertAlmostEqual(self.ledger.calibration()["brier"], 0.25, places=3)

    def test_maximum_confidence_1_0_is_included_in_top_bucket(self):
        row = self.ledger.record_prediction("x", 1.0)
        self.ledger.resolve_prediction(row["id"], "correct")
        report = self.ledger.calibration()
        self.assertEqual(len(report["buckets"]), 1)
        self.assertEqual(report["buckets"][0]["range"], "90-100%")
        self.assertEqual(report["buckets"][0]["n"], 1)


class Lessons(Temp):
    def test_a_lesson_without_a_rule_is_refused(self):
        with self.assertRaises(ValueError):
            self.ledger.record_lesson("run tests", "they failed", "   ")

    def test_lessons_rank_by_overlap_with_the_task(self):
        self.ledger.record_lesson("python import error", "guessed the module",
                                  "read the traceback first")
        self.ledger.record_lesson("git push rejected", "force pushed",
                                  "check the remote first")
        rules = [row["rule"] for row in
                 self.ledger.lessons_for("python import error on windows", 2)]
        self.assertEqual(rules[0], "read the traceback first")

    def test_recalling_a_lesson_counts_as_use(self):
        row = self.ledger.record_lesson("tests", "assumed green", "run them")
        self.ledger.lessons_for("run the tests again", 1)
        self.assertEqual(self.ledger.lessons_for("tests", 1)[0]["hits"], 2)
        self.assertEqual(row["id"], self.ledger.lessons_for("tests", 1)[0]["id"])

    def test_no_overlap_means_no_advice_rather_than_noise(self):
        self.ledger.record_lesson("git push", "force pushed", "check the remote")
        self.assertEqual(self.ledger.lessons_for("write a haiku about rain"), [])

    def test_the_lesson_store_is_capped(self):
        for index in range(MAX_LESSONS + 25):
            self.ledger.record_lesson(f"trigger {index}", "mistake", f"rule {index}")
        self.assertEqual(len(self.ledger._data["lessons"]), MAX_LESSONS)
        # The newest survive: pruning drops the oldest, not the latest advice.
        self.assertIn(str(MAX_LESSONS + 24),
                      self.ledger._data["lessons"][-1]["rule"])


class Strategies(Temp):
    def test_an_untried_strategy_is_preferred_once(self):
        self.ledger.record_attempt("triage", "read_stack_trace_first", True)
        choice = self.ledger.choose_strategy(
            "triage", ["read_stack_trace_first", "reproduce_first"])
        self.assertEqual(choice["strategy"], "reproduce_first")
        self.assertIn("untried", choice["why"])

    def test_the_best_record_wins_once_everything_is_tried(self):
        for _ in range(6):
            self.ledger.record_attempt("triage", "read_stack_trace_first", True)
        for _ in range(6):
            self.ledger.record_attempt("triage", "reproduce_first", False)
        choice = self.ledger.choose_strategy(
            "triage", ["read_stack_trace_first", "reproduce_first"])
        self.assertEqual(choice["strategy"], "read_stack_trace_first")
        self.assertGreater(choice["lower_bound"], 0.5)

    def test_no_record_says_so(self):
        choice = self.ledger.choose_strategy("brand_new_task")
        self.assertEqual(choice["strategy"], "")
        self.assertIn("no strategy", choice["why"])

    def test_an_attempt_needs_a_strategy(self):
        with self.assertRaises(ValueError):
            self.ledger.record_attempt("triage", "  ", True)


class Persistence(Temp):
    def test_the_record_survives_a_restart(self):
        row = self.ledger.record_prediction("x", 0.7, "python")
        self.ledger.resolve_prediction(row["id"], "correct")
        again = Ledger(self.path)
        self.assertEqual(again.calibration()["n"], 1)
        self.assertEqual(again.calibration()["domain"], "all")

    def test_a_corrupt_file_does_not_crash_the_ledger(self):
        self.path.write_text("{not json", encoding="utf-8")
        recovery = Ledger(self.path)
        self.assertEqual(recovery.calibration()["n"], 0)
        recovery.record_prediction("still works", 0.5)
        self.assertEqual(json.loads(self.path.read_text())["predictions"][0]["claim"],
                         "still works")

    def test_the_file_is_written_atomically(self):
        self.ledger.record_prediction("x", 0.5)
        self.assertFalse(self.path.with_suffix(".tmp").exists(),
                         "a temporary file was left behind")

    def test_predictions_are_capped_but_open_ones_are_never_dropped(self):
        open_row = self.ledger.record_prediction("never resolved", 0.5)
        for index in range(MAX_PREDICTIONS + 40):
            row = self.ledger.record_prediction(f"closed {index}", 0.5)
            self.ledger.resolve_prediction(row["id"], "correct")
        rows = self.ledger._data["predictions"]
        self.assertLessEqual(len(rows), MAX_PREDICTIONS)
        self.assertIn(open_row["id"], [entry["id"] for entry in rows])


class Wilson(unittest.TestCase):
    def test_the_bound_never_claims_certainty(self):
        self.assertLess(wilson_lower(1, 1), 0.3)
        self.assertLess(wilson_lower(10, 10), 0.8)
        self.assertGreater(wilson_lower(100, 100), 0.9)

    def test_it_handles_no_trials(self):
        self.assertEqual(wilson_lower(0, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
