"""tests/test_decision_layers.py — the four algorithms that decide something.

Not a demonstration of algorithms. Each test is a case where the simple version
gives the wrong answer: a shared-word count that ranks a stop word first, a mean
that trusts one lucky result, a threshold that goes stale, or a recommender that
cannot say no.

    shortlist.rank      which stored rule applies to what was just asked
    decision.choose     which action is worth taking, and when none is
    telemetry.Monitor   whether this turn was slower than this machine's normal
    metacog             strategy choice by UCB1, lessons by BM25
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_jarvis.autonomy_governor import AutonomyGovernor
from custom_jarvis.decision import choose, score
from custom_jarvis.metacog import Ledger
from custom_jarvis.service import CustomService
from custom_jarvis.shortlist import rank, terms
from custom_jarvis.telemetry import Monitor


class Ranking(unittest.TestCase):
    """BM25: the word that matters, not the word that is everywhere."""

    def test_a_rare_word_beats_a_word_that_appears_in_everything(self):
        documents = [
            {"id": "a", "text": "tests failed on the parser"},
            {"id": "b", "text": "tests failed on the network"},
            {"id": "c", "text": "tests failed, cors header missing"},
        ]
        best = rank("the cors tests failed", documents, limit=1)
        self.assertEqual(best[0]["id"], "c")

    def test_no_shared_word_means_no_answer(self):
        documents = [{"id": "a", "text": "git push rejected, check the remote"}]
        self.assertEqual(rank("write a haiku about rain", documents), [])

    def test_a_long_document_does_not_win_by_being_long(self):
        filler = " ".join(f"filler{index}" for index in range(60))
        documents = [
            {"id": "long", "text": f"deploy {filler}"},
            {"id": "short", "text": "deploy deploy broken build"},
        ]
        best = rank("deploy deploy", documents, limit=2)
        self.assertEqual(best[0]["id"], "short")

    def test_empty_input_is_empty_output(self):
        self.assertEqual(rank("", [{"id": "a", "text": "x"}]), [])
        self.assertEqual(rank("anything", []), [])

    def test_stop_words_are_not_terms(self):
        self.assertEqual(terms("the tests are in the build"), ["tests", "build"])

    def test_the_limit_is_respected_and_the_order_is_stable(self):
        documents = [{"id": str(index), "text": "parse the config"}
                     for index in range(6)]
        first = rank("parse config", documents, limit=3)
        second = rank("parse config", documents, limit=3)
        self.assertEqual(len(first), 3)
        self.assertEqual([row["id"] for row in first], [row["id"] for row in second])


class Deciding(unittest.TestCase):
    """Expected value: chance times worth, minus cost, minus risk."""

    def test_the_score_is_the_arithmetic_it_claims_to_be(self):
        self.assertAlmostEqual(score(p=0.5, value=2.0, cost=0.2), 0.8)
        self.assertAlmostEqual(score(p=1.0, value=1.0, risk="guarded"), 0.85)
        self.assertEqual(score(p=1.0, cost=3.0), -2.0)

    def test_the_best_expected_value_wins(self):
        result = choose([
            {"name": "guess the answer", "p": 0.6, "value": 1.0},
            {"name": "read the file first", "p": 0.95, "value": 1.0, "cost": 0.1},
        ])
        self.assertEqual(result["choice"], "read the file first")
        self.assertFalse(result["refused"])
        self.assertIn("read the file first", result["why"])
        self.assertEqual(len(result["ranked"]), 2)

    def test_nothing_is_better_than_a_guaranteed_loss(self):
        result = choose([{"name": "retry the doomed build", "p": 0.1, "value": 1.0,
                          "cost": 2.0}])
        self.assertEqual(result["choice"], "")
        self.assertTrue(result["refused"])
        self.assertIn("worth less than it costs", result["why"])

    def test_a_blocked_option_is_never_chosen(self):
        result = choose([
            {"name": "force push", "p": 1.0, "value": 9.0, "risk": "blocked"},
            {"name": "open a pull request", "p": 0.8, "value": 1.0, "risk": "guarded"},
        ])
        self.assertEqual(result["choice"], "open a pull request")
        self.assertIsNone(result["ranked"][-1]["score"])

    def test_an_impossible_probability_is_refused_loudly(self):
        with self.assertRaises(ValueError):
            score(p=1.7)
        with self.assertRaises(ValueError):
            score(p="most likely")
        with self.assertRaises(ValueError):
            score(p=0.5, risk="reckless")
        with self.assertRaises(ValueError):
            choose(["not an object"])

    def test_no_candidates_says_so(self):
        result = choose([])
        self.assertEqual(result["choice"], "")
        self.assertTrue(result["refused"])


class Pace(unittest.TestCase):
    """The baseline follows the machine instead of a number in a file."""

    def test_it_stays_quiet_until_it_knows_what_normal_is(self):
        monitor = Monitor(minimum=8)
        for _ in range(4):
            self.assertFalse(monitor.observe(1.0)["alert"])
        self.assertIn("still learning", monitor.status()["note"])

    def test_a_sudden_slowdown_is_noticed(self):
        monitor = Monitor(minimum=8)
        for index in range(14):
            monitor.observe(1.0 + (index % 2) * 0.02)
        result = monitor.observe(9.0)
        self.assertTrue(result["alert"])
        self.assertGreater(result["z"], 3.0)
        self.assertIn("standard deviations above", result["note"])
        self.assertEqual(monitor.status()["alerts"], 1)

    def test_a_steady_run_never_alerts(self):
        monitor = Monitor(minimum=8)
        for _ in range(40):
            self.assertFalse(monitor.observe(2.5)["alert"])

    def test_a_measurement_must_be_a_real_number(self):
        monitor = Monitor()
        with self.assertRaises(ValueError):
            monitor.observe(float("nan"))

    def test_the_governor_reports_its_own_pace(self):
        governor = AutonomyGovernor()
        for _ in range(14):
            governor.record_task_duration(1.0)
        governor.record_task_duration(20.0)
        pace = governor.status()["pace"]
        self.assertEqual(pace["samples"], 15)
        self.assertGreaterEqual(pace["alerts"], 1)
        self.assertIn("slow", pace["note"] + "slow")


class Learned(unittest.TestCase):
    """The ledger's own choice points now use those algorithms."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.folder.name) / "metacog.json")

    def tearDown(self):
        self.folder.cleanup()

    def test_a_lesson_with_the_rare_word_comes_back_first(self):
        self.ledger.record_lesson("the build fails", "assumed green",
                                  "run the build")
        self.ledger.record_lesson("the build fails on cors", "guessed the header",
                                  "check the access-control header")
        rules = [row["rule"] for row in
                 self.ledger.lessons_for("build fails, cors header missing", 2)]
        self.assertEqual(rules[0], "check the access-control header")

    def test_an_unrelated_lesson_is_not_offered(self):
        self.ledger.record_lesson("git push rejected", "force pushed",
                                  "check the remote first")
        self.assertEqual(self.ledger.lessons_for("write a haiku about rain"), [])

    def test_strategy_choice_explains_itself_with_the_bandit(self):
        for _ in range(6):
            self.ledger.record_attempt("triage", "read_the_trace", True)
        for _ in range(6):
            self.ledger.record_attempt("triage", "reproduce_first", False)
        choice = self.ledger.choose_strategy("triage", ["read_the_trace",
                                                       "reproduce_first"])
        self.assertEqual(choice["strategy"], "read_the_trace")
        self.assertGreater(choice["ucb"], 1.0)
        self.assertIn("UCB1", choice["why"])

    def test_a_single_lucky_attempt_gets_tested_rather_than_trusted(self):
        # 1 of 1 looks perfect and proves nothing, so UCB1 spends one more turn
        # on it. That is exploration, not gullibility.
        self.ledger.record_attempt("deploy", "try_it_and_see", True)
        for _ in range(12):
            self.ledger.record_attempt("deploy", "run_the_tests", True)
        first = self.ledger.choose_strategy("deploy", ["try_it_and_see", "run_the_tests"])
        self.assertEqual(first["strategy"], "try_it_and_see")
        self.assertLess(first["lower_bound"], 0.5)

        # Once the shortcut fails a few times, the proven approach returns.
        for _ in range(3):
            self.ledger.record_attempt("deploy", "try_it_and_see", False)
        again = self.ledger.choose_strategy("deploy", ["try_it_and_see", "run_the_tests"])
        self.assertEqual(again["strategy"], "run_the_tests")


class AsATool(unittest.TestCase):
    """The decision layer is reachable by the assistant, and free of prompts."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.base = Path(self.folder.name)
        self.asked = []

        def approval(kind, *rest):
            self.asked.append(kind)
            return True

        self.service = CustomService(self.base / "state", approval=approval)
        workspace = self.base / "ws"
        workspace.mkdir(parents=True, exist_ok=True)
        self.service.perform("set_workspace", {"path": str(workspace)})

    def tearDown(self):
        self.folder.cleanup()

    def test_decide_is_registered_and_returns_a_choice(self):
        names = {row["name"] for row in self.service.perform("list_tools", {})}
        self.assertIn("decide", names)
        result = self.service.perform("run_skill", {"id": "meta_confidence"})
        self.assertTrue(result["success"])

    def test_deciding_does_not_ask_permission(self):
        result = self.service.perform("tool", {
            "name": "decide",
            "arguments": {"options": [
                {"name": "ask the user", "p": 0.9, "value": 1.0, "cost": 0.1},
                {"name": "guess", "p": 0.3, "value": 1.0},
            ]},
        })
        self.assertTrue(result["success"], result)
        self.assertIn("ask the user", result["output"])
        # Choosing the workspace asked once, as it should. Deciding asked nothing.
        self.assertEqual(self.asked, ["set_workspace"])

    def test_a_bad_probability_comes_back_as_an_error_not_a_crash(self):
        result = self.service.perform("tool", {
            "name": "decide",
            "arguments": {"options": [{"name": "wishful", "p": 4.0}]},
        })
        self.assertFalse(result["success"])
        self.assertIn("between 0.0 and 1.0", result["error"])


if __name__ == "__main__":
    unittest.main()
