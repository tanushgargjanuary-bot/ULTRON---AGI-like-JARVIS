"""The verifiers are part of the product: they must not rot.

They are the only way to answer "does this actually work on my machine", so a
verifier that crashes on `--help`, or that stops being wired into the runner,
silently turns a real answer into a cheerful lie. These tests are cheap and they
guard exactly that.

Nothing here runs a verifier for real: `--help` must parse the whole module and
every import at module level, which is where rot shows up first.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

VERIFIERS = [
    "verify_windows.py",
    "verify_display.py",
    "verify_capture.py",
    "verify_audio.py",
    "verify_browser.py",
    "verify_all.py",
]


class VerifierTests(unittest.TestCase):
    def test_every_verifier_exists(self):
        for name in VERIFIERS:
            with self.subTest(script=name):
                self.assertTrue((SCRIPTS / name).is_file(), f"{name} is missing")

    def test_every_verifier_answers_help(self):
        for name in VERIFIERS:
            with self.subTest(script=name):
                done = subprocess.run(
                    [sys.executable, str(SCRIPTS / name), "--help"],
                    capture_output=True, text=True, timeout=180, cwd=str(ROOT),
                )
                self.assertEqual(done.returncode, 0, done.stderr[-800:])
                self.assertIn("usage", done.stdout.lower())

    def test_runner_knows_each_verifier(self):
        module = self._runner()
        wired = {entry[1] for entry in module.VERIFIERS}
        for name in VERIFIERS:
            if name == "verify_all.py":
                continue
            with self.subTest(script=name):
                self.assertIn(name, wired, f"{name} is never run by verify_all.py")
                self.assertTrue((SCRIPTS / name).is_file())

    def test_runner_reports_skip_as_not_a_failure(self):
        """A SKIP must never be counted as a failure — the whole point."""
        module = self._runner()
        self.assertEqual(module.verdict_for({"passed": 3, "failed": 0, "skipped": 0}),
                         "WORKS")
        self.assertEqual(module.verdict_for({"passed": 2, "failed": 0, "skipped": 14}),
                         "PARTLY TESTED")
        self.assertEqual(module.verdict_for({"passed": 0, "failed": 0, "skipped": 5}),
                         "NOT TESTED HERE")
        self.assertEqual(module.verdict_for({"passed": 1, "failed": 1, "skipped": 0}),
                         "BROKEN")

    @staticmethod
    def _runner():
        import importlib.util

        spec = importlib.util.spec_from_file_location("verify_all_mod",
                                                     SCRIPTS / "verify_all.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


if __name__ == "__main__":
    unittest.main()
