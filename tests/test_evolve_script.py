"""tests/test_evolve_script.py — the engine that turns the loop.

    Two things need proving: that the measurement finds a real improvement when
    one exists, and that it refuses to invent one when none does. The second is
    the one that keeps this honest — a tuner that always proposes something is
    indistinguishable from a random number generator with a log file.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import evolve


class CaseBuildingTests(unittest.TestCase):
    def test_the_built_in_fixture_has_both_kinds_of_case(self):
        cases, phrases = evolve.build_cases()
        self.assertGreater(len(cases), 10)
        self.assertTrue(any(case.safety for case in cases))
        self.assertTrue(any(not case.safety for case in cases))
        self.assertTrue(all(case.id in phrases for case in cases))

    def test_junk_phrases_are_safety_cases(self):
        cases, phrases = evolve.build_cases()
        junk = [case for case in cases if not phrases[case.id]]
        self.assertTrue(junk)
        self.assertTrue(all(case.safety for case in junk))

    def test_a_csv_adds_cases_and_skips_its_header(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mine.csv"
            path.write_text("spoken,expected\nwhts app,WhatsApp\nqwerty zx,\n", encoding="utf-8")
            cases, phrases = evolve.build_cases(path)
        self.assertIn("whts app", phrases)
        self.assertEqual(phrases["whts app"], "WhatsApp")
        self.assertNotIn("spoken", phrases)
        self.assertTrue(any(case.id == "qwerty zx" and case.safety for case in cases))

    def test_a_missing_csv_is_not_an_error(self):
        cases, _ = evolve.build_cases(Path("/nonexistent/mine.csv"))
        self.assertTrue(cases)


class MeasurementTests(unittest.TestCase):
    def test_a_floor_that_is_already_right_is_not_changed(self):
        cases, phrases = evolve.build_cases()
        payload = evolve.run(cases, phrases, current=0.75)
        self.assertFalse(payload["verdict"]["accepted"])
        self.assertIn("better by enough", payload["verdict"]["reason"])

    def test_a_floor_that_is_too_strict_is_corrected(self):
        cases, phrases = evolve.build_cases()
        payload = evolve.run(cases, phrases, current=0.95)
        verdict = payload["verdict"]
        self.assertTrue(verdict["accepted"], verdict["reason"])
        self.assertLess(verdict["value"], 0.95)
        self.assertLess(verdict["comparison"]["p_value"], 0.05)
        self.assertEqual(verdict["comparison"]["losses"], 0)

    def test_the_evaluator_never_rewards_matching_junk(self):
        cases, phrases = evolve.build_cases()
        evaluator = evolve.ThresholdEvaluator(cases, phrases)
        junk = next(case for case in cases if case.safety)
        for floor in (0.4, 0.6, 0.8, 0.95):
            with self.subTest(floor=floor):
                self.assertIn(evaluator.score(floor, junk), (0.0, 1.0))

    def test_a_verdict_names_the_artefact_it_is_about(self):
        cases, phrases = evolve.build_cases()
        payload = evolve.run(cases, phrases, current=0.75)
        self.assertEqual(payload["artefact"], "app_resolver.fuzzy_floor")
        self.assertIn("cases", payload)


class LoggingTests(unittest.TestCase):
    def test_a_finding_is_appended_not_overwritten(self):
        cases, phrases = evolve.build_cases()
        payload = evolve.run(cases, phrases, current=0.95)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evolution-log.json"
            evolve.record(payload, path=path)
            evolve.record(payload, path=path)
            stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(stored["entries"]), 2)
        self.assertEqual(stored["entries"][0]["artefact"], "app_resolver.fuzzy_floor")
        self.assertIn("p_value", stored["entries"][0])

    def test_a_corrupt_log_is_replaced_rather_than_crashing(self):
        cases, phrases = evolve.build_cases()
        payload = evolve.run(cases, phrases, current=0.95)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evolution-log.json"
            path.write_text("{not json", encoding="utf-8")
            evolve.record(payload, path=path)
            stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(stored["entries"]), 1)

    def test_a_rejection_is_recorded_too(self):
        """The rejections are the evidence that the loop is not just collecting changes."""
        cases, phrases = evolve.build_cases()
        payload = evolve.run(cases, phrases, current=0.75)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evolution-log.json"
            evolve.record(payload, path=path)
            entry = json.loads(path.read_text(encoding="utf-8"))["entries"][0]
        self.assertEqual(entry["before"], entry["after"])


class CommandTests(unittest.TestCase):
    def _run(self, *argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = evolve.main(list(argv))
        return code, buffer.getvalue()

    def test_the_command_says_it_changed_nothing(self):
        code, output = self._run("--no-log")
        self.assertEqual(code, 0)
        self.assertIn("never edits source code", output)
        self.assertIn("accepted   False", output)

    def test_json_output_is_parseable(self):
        _, output = self._run("--no-log", "--json")
        payload = json.loads(output)
        self.assertEqual(payload["artefact"], "app_resolver.fuzzy_floor")
        self.assertIn("verdict", payload)

    def test_no_log_means_no_file_is_written(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evolution-log.json"
            original = evolve.LOG_PATH
            evolve.LOG_PATH = path
            try:
                self._run("--no-log")
                self.assertFalse(path.exists())
            finally:
                evolve.LOG_PATH = original

    def test_the_log_is_written_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evolution-log.json"
            original = evolve.LOG_PATH
            evolve.LOG_PATH = path
            try:
                self._run()
                self.assertTrue(path.exists())
            finally:
                evolve.LOG_PATH = original


if __name__ == "__main__":
    unittest.main()
