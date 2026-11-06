"""The proof gate's verdicts must not be able to round up.

Every other instrument in this project reports what a check found. This one is
the gate that decides whether a *claim about the product* holds, so its failure
mode is not a wrong line in a log — it is the word PROVEN appearing next to
something that was never demonstrated. These tests pin the arithmetic that stops
that, in the order the verdicts outrank each other:

    FAILED  >  NOT PRESENT  >  PARTIAL  >  PROVEN

and the rule that a single skipped step is enough to stop a claim being PROVEN,
because "I could not test half of it" is not "it works".
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load():
    spec = importlib.util.spec_from_file_location("proof_gate", SCRIPTS / "proof_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.gate = load()

    def _verdict(self, *statuses):
        claim = self.gate.Claim("k", "a claim", "a requirement")
        for index, status in enumerate(statuses):
            claim.step(f"step{index}", status, "")
        return claim.verdict()

    def test_all_steps_proven_is_proven(self):
        self.assertEqual(self._verdict(*(self.gate.PROVEN,) * 4), self.gate.PROVEN)

    def test_one_failure_anywhere_fails_the_claim(self):
        self.assertEqual(self._verdict(self.gate.PROVEN, self.gate.PROVEN,
                                       self.gate.FAILED), self.gate.FAILED)

    def test_one_skip_stops_a_claim_being_proven(self):
        verdict = self._verdict(self.gate.PROVEN, self.gate.PROVEN, self.gate.SKIPPED)
        self.assertEqual(verdict, "PARTIAL")
        self.assertNotEqual(verdict, self.gate.PROVEN)

    def test_nothing_skipped_is_not_present(self):
        self.assertEqual(self._verdict(self.gate.SKIPPED, self.gate.SKIPPED),
                         "PARTIAL", "skipped work is not missing code")

    def test_missing_code_is_named_as_missing(self):
        self.assertEqual(self._verdict(self.gate.MISSING), self.gate.MISSING)

    def test_missing_early_evidence_is_missing_not_partial(self):
        """No evidence at all, only absence — say NOT PRESENT even if later steps
        could not run either."""
        self.assertEqual(self._verdict(self.gate.MISSING, self.gate.SKIPPED,
                                       self.gate.SKIPPED), self.gate.MISSING)

    def test_partial_evidence_plus_missing_code_is_partial(self):
        self.assertEqual(self._verdict(self.gate.PROVEN, self.gate.MISSING), "PARTIAL")

    def test_a_claim_with_no_steps_is_not_a_pass(self):
        self.assertEqual(self.gate.Claim("k", "t", "r").verdict(), self.gate.MISSING)

    def test_failure_outranks_missing(self):
        self.assertEqual(self._verdict(self.gate.FAILED, self.gate.MISSING),
                         self.gate.FAILED)


class ClaimTableTests(unittest.TestCase):
    def setUp(self):
        self.gate = load()

    def test_every_claim_has_a_title_and_a_requirement(self):
        for key, title, requirement, fn in self.gate.CLAIMS:
            with self.subTest(claim=key):
                self.assertTrue(title, f"{key} has no title")
                self.assertTrue(requirement, f"{key} names no requirement it serves")
                self.assertTrue(callable(fn))

    def test_claim_keys_are_unique(self):
        keys = [key for key, _t, _r, _f in self.gate.CLAIMS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_the_acceptance_criteria_are_all_represented(self):
        """The standing criteria must each own a claim, or the gate silently
        stops covering something the user asked for."""
        keys = {key for key, _t, _r, _f in self.gate.CLAIMS}
        for required in ("voice_in", "voice_out", "sees_screen", "consent",
                         "focus_safe", "memory_approval", "persona",
                         "provider_switch", "budgets"):
            with self.subTest(claim=required):
                self.assertIn(required, keys)

    def test_a_subset_run_exits_zero_and_says_a_verdict(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / "proof_gate.py"),
                               "--only", "persona"], capture_output=True, text=True,
                              timeout=300, cwd=str(ROOT))
        self.assertEqual(done.returncode, 0, done.stderr[-600:])
        self.assertIn("PROOF GATE", done.stdout)
        self.assertIn("persona", done.stdout)


if __name__ == "__main__":
    unittest.main()


class StoreSnapshotTests(unittest.TestCase):
    """The digest claim compares the memory folder before and after a build.

    It used to count bytecode. On a clean clone the first run writes
    `memory/__pycache__/*.pyc`, so the claim failed on a program that had done
    nothing — a false accusation, which is the one failure mode a proof gate must
    not have. These tests pin the rule: bytecode and editor droppings are not the
    user's memory, everything else is.
    """

    def setUp(self):
        import tempfile
        self.root = Path(tempfile.mkdtemp(prefix="store-state-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        (self.root / "long_term.json").write_text('{"a": 1}', encoding="utf-8")
        self.gate = _load_gate()

    def test_bytecode_appearing_is_not_a_change(self):
        before = self.gate._store_state(self.root)
        cache = self.root / "__pycache__"
        cache.mkdir()
        (cache / "memory_manager.cpython-312.pyc").write_bytes(b"\x00\x00")
        self.assertEqual(self.gate._store_state(self.root), before)

    def test_a_real_file_changing_is_a_change(self):
        before = self.gate._store_state(self.root)
        (self.root / "long_term.json").write_text('{"a": 2, "b": 3}', encoding="utf-8")
        self.assertNotEqual(self.gate._store_state(self.root), before)

    def test_a_new_fact_is_a_change(self):
        before = self.gate._store_state(self.root)
        (self.root / "reminders.json").write_text("[]", encoding="utf-8")
        self.assertNotEqual(self.gate._store_state(self.root), before)


def _load_gate():
    """Import scripts/proof_gate.py by path, the way the gate tests already do."""
    path = Path(__file__).resolve().parents[1] / "scripts" / "proof_gate.py"
    spec = importlib.util.spec_from_file_location("proof_gate_for_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
